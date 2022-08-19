# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 Virtual Cable S.L.
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
"""
@author: Adolfo Gómez, dkmaster at dkmon dot com
"""

import logging
import typing

from uds import models

from .. import test, generators, rest, constants
from ... import fixtures

from uds.REST.handlers import AUTH_TOKEN_HEADER

NUMBER_OF_ITEMS_TO_CREATE = 4


class RESTTestCase(test.UDSTransactionTestCasse):
    # Authenticators related
    auth: models.Authenticator
    groups: typing.List[models.Group]
    admins: typing.List[models.User]
    staffs: typing.List[models.User]
    plain_users: typing.List[models.User]

    user_service: models.UserService

    def setUp(self) -> None:
        # Set up data for REST Test cases
        # First, the authenticator related
        self.auth = fixtures.authenticators.createAuthenticator()
        self.groups = fixtures.authenticators.createGroups(
            self.auth, NUMBER_OF_ITEMS_TO_CREATE
        )
        # Create some users, one admin, one staff and one user
        self.admins = fixtures.authenticators.createUsers(
            self.auth,
            number_of_users=NUMBER_OF_ITEMS_TO_CREATE,
            is_admin=True,
            groups=self.groups,
        )
        self.staffs = fixtures.authenticators.createUsers(
            self.auth,
            number_of_users=NUMBER_OF_ITEMS_TO_CREATE,
            is_staff=True,
            groups=self.groups,
        )
        self.plain_users = fixtures.authenticators.createUsers(
            self.auth, number_of_users=NUMBER_OF_ITEMS_TO_CREATE, groups=self.groups
        )

        self.user_service = fixtures.services.createSingleTestingUserServiceStructure(
            self.admins[0], self.groups
        )

    @staticmethod
    def register_data(chars: typing.Optional[str] = None) -> typing.Dict[str, str]:
        # Data for registration
        return {
            'username': generators.random_string(size=12, chars=chars)
            + '@AUTH'
            + generators.random_string(size=12, chars=chars),
            'hostname': generators.random_string(size=48, chars=chars),
            'ip': generators.random_ip(),
            'mac': generators.random_mac(),
            'pre_command': generators.random_string(size=64, chars=chars),
            'run_once_command': generators.random_string(size=64, chars=chars),
            'post_command': generators.random_string(size=64, chars=chars),
            'log_level': '0',
        }

    def login(
        self, user: typing.Optional[models.User] = None, as_admin: bool = True
    ) -> str:
        '''
        Login as specified and returns the auth token
        The token is inserted on the header of the client, so it can be used in the rest of the tests
        '''
        user = user or (self.admins[0] if as_admin else self.staffs[0])
        response = rest.login(
            self,
            self.client,
            auth_id=self.auth.uuid,
            username=user.name,
            password=user.name,
        )
        self.assertEqual(response['result'], 'ok', 'Login failed')
        # Insert token into headers
        self.client.add_header(AUTH_TOKEN_HEADER, response['token'])
        return response['token']

    # Login as admin or staff and register an actor
    # Returns as a tuple the auth token and the actor registration result token:
    #   - The login auth token
    #   - The actor token
    def login_and_register(self, as_admin: bool = True) -> typing.Tuple[str, str]:
        token = self.login(as_admin=as_admin)  # Token not used, alreade inserted on login
        response = self.client.post(
            '/uds/rest/actor/v3/register',
            data=self.register_data(constants.STRING_CHARS),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, 'Actor registration failed')
        return token, response.json()['result']
