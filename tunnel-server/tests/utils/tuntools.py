# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 Virtual Cable S.L.U.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright notice,
#      this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright notice,
#      this list of conditions and the following disclaimer in the documentation
#      and/or other materials provided with the distribution.
#    * Neither the name of Virtual Cable S.L. nor the names of its contributors
#      may be used to endorse or promote products derived from this software
#      without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
'''
Author: Adolfo Gómez, dkmaster at dkmon dot com
'''
import asyncio
import contextlib
import collections.abc
import json
import logging
import multiprocessing
import os
import random
import socket
import ssl
import string
import tempfile
import typing
import copy
from unittest import mock

import udstunnel
from uds_tunnel import config, consts, stats, tunnel

from . import certs, conf, fixtures, tools

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    from asyncio.subprocess import Process


@contextlib.contextmanager
def create_config_file(
    listen_host: str,
    listen_port: int,
    **kwargs,
) -> typing.Generator[str, None, None]:
    cert, key, password = certs.selfSignedCert(listen_host, use_password=True)
    # Create the certificate file on /tmp
    cert_file: str = ''
    with tempfile.NamedTemporaryFile(prefix='cert-', mode='w', delete=False) as f:
        f.write(key)
        f.write(cert)
        cert_file = f.name

    # Config file for the tunnel, ignore readed

    values: typing.Dict[str, typing.Any] = copy.copy(kwargs)
    values.update(
        {
            'address': listen_host,
            'port': listen_port,
            'ipv6': ':' in listen_host,
            'loglevel': 'DEBUG',
            'ssl_certificate': cert_file,
            'ssl_certificate_key': '',
            'ssl_password': password,
            'ssl_ciphers': '',
            'ssl_dhparam': '',
        }
    )
    values, cfg = fixtures.get_config(  # pylint: disable=unused-variable
        **values,
    )
    # Write config file
    cfgfile: str = ''
    with tempfile.NamedTemporaryFile(prefix='conf-', mode='w', delete=False) as f:
        f.write(fixtures.TEST_CONFIG.format(**values))
        cfgfile = f.name

    try:
        yield cfgfile
    finally:
        # Remove the files if they exists
        for filename in (cfgfile, cert_file):
            try:
                os.remove(filename)
            except Exception:
                logger.warning('Error removing %s', filename)


@contextlib.asynccontextmanager
async def create_tunnel_proc(
    listen_host: str,
    listen_port: int,
    remote_host: str = '0.0.0.0',  # nosec: intentionally value, Not used if response is provided
    remote_port: int = 0,  # Not used if response is provided
    *,
    response: typing.Optional[
        typing.Union[
            typing.Callable[[bytes], typing.Mapping[str, typing.Any]],
            typing.Mapping[str, typing.Any],
        ]
    ] = None,
    use_fake_http_server: bool = False,
    global_stats: typing.Optional[stats.GlobalStats] = None,
    # Configuration parameters
    **kwargs,
) -> collections.abc.AsyncGenerator[
    typing.Tuple['config.ConfigurationType', typing.Optional[asyncio.Queue[bytes]]],
    None,
]:
    """Creates a "tunnel proc" server, that is, a tunnel server that will be
       invoked by udstunnel subpoocesses.

    Args:
        listen_host (str): Host to listen on
        listen_port (int): Port to listen on
        remote_host (str): Remote host to connect to
        remote_port (int): Remote port to connect to
        response (typing.Optional[typing.Union[typing.Callable[[bytes], typing.Mapping[str, typing.Any]], typing.Mapping[str, typing.Any]]], optional): Response to send to the client. Defaults to None.
        use_fake_http_server (bool, optional): If True, a fake http server will be used instead of a mock. Defaults to False.

    Yields:
        collections.abc.AsyncGenerator[typing.Tuple[config.ConfigurationType, typing.Optional[asyncio.Queue[bytes]]], None]: A tuple with the configuration
            and a queue with the data received by the "fake_http_server" if used, or None if not used
    """

    # Ensure response
    if response is None:
        response = conf.UDS_GET_TICKET_RESPONSE(remote_host, remote_port)

    port = random.randint(20000, 40000)  # nosec  Just a random port
    hhost = f'[{listen_host}]' if ':' in listen_host else listen_host
    args = {
        'uds_server': f'http://{hhost}:{port}/uds/rest',
    }
    args.update(kwargs)  # Add extra args
    # If use http server instead of mock
    # We will setup a different context provider
    if use_fake_http_server:
        resp = conf.UDS_GET_TICKET_RESPONSE(remote_host, remote_port)

        @contextlib.asynccontextmanager
        async def provider() -> collections.abc.AsyncGenerator[typing.Optional[asyncio.Queue[bytes]], None]:
            async with create_fake_broker_server(listen_host, port, response=response or resp) as queue:
                try:
                    yield queue
                finally:
                    pass

    else:

        @contextlib.asynccontextmanager
        async def provider() -> collections.abc.AsyncGenerator[typing.Optional[asyncio.Queue[bytes]], None]:
            with mock.patch(
                'uds_tunnel.tunnel.TunnelProtocol._read_from_uds',
                new_callable=tools.AsyncMock,
            ) as m:
                if callable(response):
                    m.side_effect = lambda cfg, ticket, *args, **kwargs: response(ticket)  # type: ignore
                else:
                    m.return_value = response
                try:
                    yield None
                finally:
                    pass

    with create_config_file(listen_host, listen_port, **args) as cfgfile:
        args = mock.MagicMock()
        # Config can be a file-like or a path
        args.config = cfgfile
        args.ipv6 = False  # got from config file

        # Load config here also for testing
        cfg = config.read(cfgfile)

        async with provider() as possible_queue:
            # Stats collector
            global_stats = global_stats or stats.GlobalStats()  # If none provided, create a new one
            # Pipe to send data to tunnel
            own_end, other_end = multiprocessing.Pipe()

            udstunnel.setup_log(cfg)

            # Clear the stop flag
            udstunnel.do_stop.clear()

            # Create the tunnel task
            task = asyncio.create_task(udstunnel.tunnel_proc_async(other_end, cfg, global_stats.ns))

            # Server listening for connections
            server_socket = socket.socket(
                socket.AF_INET6 if ':' in listen_host else socket.AF_INET, socket.SOCK_STREAM
            )
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Allow reuse of address
            server_socket.bind((listen_host, listen_port))
            server_socket.listen(8)
            server_socket.setblocking(False)

            async def server():
                loop = asyncio.get_running_loop()
                try:
                    while True:
                        client, addr = await loop.sock_accept(server_socket)
                        # Send the socket to the tunnel
                        own_end.send((client.dup(), addr))
                        client.close()
                except asyncio.CancelledError:
                    pass  # We are closing
                except Exception:
                    logger.exception('Exception in server')
                # Close the socket
                server_socket.close()

            # Create the middleware task
            server_task = asyncio.create_task(server())
            try:
                yield cfg, possible_queue
            finally:
                # Cancel the middleware task
                server_task.cancel()
                logger.info('Server closed')

                # Close the pipe (both ends)
                own_end.close()

                task.cancel()
                # wait for the task to finish
                await task

                # Ensure log file are removed
                rootlog = logging.getLogger()
                for h in rootlog.handlers:
                    if isinstance(h, logging.FileHandler):
                        h.close()
                        # Remove the file if possible, do not fail
                        try:
                            os.unlink(h.baseFilename)
                        except Exception:
                            logger.warning('Could not remove log file %s', h.baseFilename)


async def create_tunnel_server(cfg: 'config.ConfigurationType', context: 'ssl.SSLContext') -> 'asyncio.Server':
    # Create fake proxy
    proxy = mock.MagicMock()
    proxy.cfg = cfg
    proxy.ns = mock.MagicMock()
    proxy.ns.current = 0
    proxy.ns.total = 0
    proxy.ns.sent = 0
    proxy.ns.recv = 0
    proxy.counter = 0

    loop = asyncio.get_running_loop()

    # Create an asyncio listen socket on cfg.listen_host:cfg.listen_port
    return await loop.create_server(
        lambda: tunnel.TunnelProtocol(proxy),
        cfg.listen_address,
        cfg.listen_port,
        ssl=context,
        family=socket.AF_INET6 if cfg.ipv6 or ':' in cfg.listen_address else socket.AF_INET,
    )


@contextlib.asynccontextmanager
async def create_test_tunnel(
    *,
    callback: typing.Callable[[bytes], None],
    port: typing.Optional[int] = None,
    remote_port: typing.Optional[int] = None,
    # Configuration parameters
    **kwargs: typing.Any,
) -> collections.abc.AsyncGenerator['config.ConfigurationType', None]:
    # Generate a listening server for testing tunnel
    # Prepare the end of the tunnel
    async with tools.AsyncTCPServer(
        port=remote_port or 54876, callback=callback, name='create_test_tunnel'
    ) as server:
        # Create a tunnel to localhost 13579
        # SSl cert for tunnel server
        with certs.ssl_context() as (ssl_ctx, _):
            _, cfg = fixtures.get_config(
                address=server.host,
                port=port or 7771,
                ipv6=':' in server.host,
                **kwargs,
            )
            with mock.patch(
                'uds_tunnel.tunnel.TunnelProtocol._read_from_uds',
                new_callable=tools.AsyncMock,
            ) as m:
                m.return_value = conf.UDS_GET_TICKET_RESPONSE(server.host, server.port)

                tunnel_server = await create_tunnel_server(cfg, ssl_ctx)
                try:
                    yield cfg
                finally:
                    tunnel_server.close()
                    await tunnel_server.wait_closed()


@contextlib.asynccontextmanager
async def create_fake_broker_server(
    host: str,
    port: int,
    *,
    response: typing.Optional[
        typing.Union[
            typing.Callable[[bytes], typing.Mapping[str, typing.Any]],
            typing.Mapping[str, typing.Any],
        ]
    ],
) -> collections.abc.AsyncGenerator[asyncio.Queue[bytes], None]:
    # crate a fake broker server
    # Ignores request, and sends response
    # if is a callable, it will be called to get the response and encode it as json

    # to content the server request
    data: bytes = b''
    requests: asyncio.Queue[bytes] = asyncio.Queue()

    async def processor(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        nonlocal data
        nonlocal response

        while readed := await reader.read(1024):
            data += readed
            # If data ends in \r\n\r\n, we have the full request
            if data.endswith(b'\r\n\r\n'):
                requests.put_nowait(data)
                break

        if callable(response):
            rr = response(data)
        else:
            rr = response or {}

        resp: bytes = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n' + json.dumps(rr).encode()

        data = b''  # reset data for next
        # send response
        writer.write(resp)
        await writer.drain()
        # And close
        writer.close()

    async with tools.AsyncTCPServer(
        host=host, port=port, processor=processor, name='create_fake_broker_server'
    ) as server:  # pylint: disable=unused-variable
        try:
            yield requests
        finally:
            pass  # nothing to do


@contextlib.asynccontextmanager
async def open_tunnel_client(
    cfg: 'config.ConfigurationType',
    use_tunnel_handshake: bool = False,
    local_port: typing.Optional[int] = None,
    skip_ssl: bool = False,  # Onlt valid if use_tunnel_handshake is False
) -> collections.abc.AsyncGenerator[typing.Tuple[asyncio.StreamReader, asyncio.StreamWriter], None]:
    """opens an ssl socket to the tunnel server"""
    loop = asyncio.get_running_loop()
    family = socket.AF_INET6 if cfg.ipv6 or ':' in cfg.listen_address else socket.AF_INET
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    if not use_tunnel_handshake:
        if not skip_ssl:
            reader, writer = await asyncio.open_connection(
                cfg.listen_address, cfg.listen_port, family=family, ssl=context, ssl_handshake_timeout=1
            )
        else:
            reader, writer = await asyncio.open_connection(cfg.listen_address, cfg.listen_port, family=family)
    else:
        # Open the socket, send handshake and then upgrade to ssl, non blocking
        sock = socket.socket(family, socket.SOCK_STREAM)
        if local_port:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('', local_port))
        # Set socket to non blocking
        sock.setblocking(False)
        await loop.sock_connect(sock, (cfg.listen_address, cfg.listen_port))
        await loop.sock_sendall(sock, consts.HANDSHAKE_V1)
        # Note, we need an small delay, because the "middle connection", in case of tunnel proc,
        # that will simulate the tunnel handshake processor is running over a bufferedReader
        # (reads chunks of 4096 bytes). If we don't wait, the handshake will be readed
        # and part or all of ssl handshake also.
        # With uvloop this seems to be not needed, but with asyncio it is.
        # upgrade to ssl
        reader, writer = await asyncio.open_connection(
            sock=sock, ssl=context, server_hostname=cfg.listen_address
        )
    try:
        yield reader, writer
    finally:
        writer.close()
        await writer.wait_closed()


@contextlib.asynccontextmanager
async def tunnel_app_runner(
    host: typing.Optional[str] = None,
    port: typing.Optional[int] = None,
    *,
    wait_for_port: bool = False,
    args: typing.Optional[typing.List[str]] = None,
    **kwargs: typing.Union[str, int, bool],
) -> collections.abc.AsyncGenerator['Process', None]:
    # Ensure we are on src directory
    if os.path.basename(os.getcwd()) != 'src':
        os.chdir('src')

    host = host or '127.0.0.1'
    port = port or 7799
    # Execute udstunnel as application, using asyncio.create_subprocess_exec
    # First, create the configuration file
    with create_config_file(host, port, **kwargs) as config_file:
        args = args or ['-t', '-c', config_file]
        process = await asyncio.create_subprocess_exec(
            'python',
            '-m',
            'udstunnel',
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        if wait_for_port:
            # Ensure port is listening
            await tools.wait_for_port(host, port)

        try:
            yield process
        finally:
            # Ensure the process is terminated
            if process.returncode is None:
                logger.info('Terminating tunnel process %s', process.pid)
                process.terminate()
                await asyncio.wait_for(process.wait(), 10)
                # Ensure the process is terminated
                if process.returncode is None:
                    logger.info('Killing tunnel process %s', process.pid)
                    process.kill()
                    await asyncio.wait_for(process.wait(), 10)
                logger.info('Tunnel process %s terminated', process.pid)


def get_correct_ticket(length: int = consts.TICKET_LENGTH, *, prefix: typing.Optional[str] = None) -> bytes:
    """Returns a ticket with the correct length"""
    prefix = prefix or ''
    return (
        ''.join(
            random.choice(string.ascii_letters + string.digits)
            for _ in range(length - len(prefix))  # nosec just for tests
        ).encode()
        + prefix.encode()
    )
