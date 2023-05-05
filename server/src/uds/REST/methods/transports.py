# -*- coding: utf-8 -*-

#
# Copyright (c) 2014-2021 Virtual Cable S.L.U.
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
#    * Neither the name of Virtual Cable S.L.U. nor the names of its contributors
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
@itemor: Adolfo Gómez, dkmaster at dkmon dot com
'''
import re
import logging
import typing

from django.utils.translation import gettext_lazy as _, gettext
from uds.models import Transport, Network, ServicePool
from uds.core import transports
from uds.core.ui import gui
from uds.core.util import permissions
from uds.core.util import os_detector as OsDetector

from uds.REST.model import ModelHandler


logger = logging.getLogger(__name__)

# Enclosed methods under /item path


class Transports(ModelHandler):
    model = Transport
    save_fields = [
        'name',
        'comments',
        'tags',
        'priority',
        'nets_positive',
        'allowed_oss',
        'label',
    ]

    table_title = _('Transports')
    table_fields = [
        {'priority': {'title': _('Priority'), 'type': 'numeric', 'width': '6em'}},
        {'name': {'title': _('Name'), 'visible': True, 'type': 'iconType'}},
        {'type_name': {'title': _('Type')}},
        {'comments': {'title': _('Comments')}},
        {
            'pools_count': {
                'title': _('Service Pools'),
                'type': 'numeric',
                'width': '6em',
            }
        },
        {'allowed_oss': {'title': _('Devices'), 'width': '8em'}},
        {'tags': {'title': _('tags'), 'visible': False}},
    ]

    def enum_types(self) -> typing.Iterable[typing.Type[transports.Transport]]:
        return transports.factory().providers().values()

    def getGui(self, type_: str) -> typing.List[typing.Any]:
        transport = transports.factory().lookup(type_)

        if not transport:
            raise self.invalidItemException()

        field = self.addDefaultFields(
            transport.guiDescription(), ['name', 'comments', 'tags', 'priority']
        )
        field = self.addField(
            field,
            {
                'name': 'nets_positive',
                'value': True,
                'label': gettext('Network access'),
                'tooltip': gettext(
                    'If checked, the transport will be enabled for the selected networks. If unchecked, transport will be disabled for selected networks'
                ),
                'type': 'checkbox',
                'order': 100,  # At end
            },
        )
        field = self.addField(
            field,
            {
                'name': 'networks',
                'value': [],
                'values': sorted(
                    [{'id': x.uuid, 'text': x.name} for x in Network.objects.all()],
                    key=lambda x: x['text'].lower(),  # type: ignore
                ),
                'label': gettext('Networks'),
                'tooltip': gettext(
                    'Networks associated with this transport. If No network selected, will mean "all networks"'
                ),
                'type': 'multichoice',
                'order': 101,
            },
        )
        field = self.addField(
            field,
            {
                'name': 'allowed_oss',
                'value': [],
                'values': sorted(
                    [
                        {'id': x.name, 'text': x.name}
                        for x in OsDetector.knownOss
                    ],
                    key=lambda x: x['text'].lower(),
                ),
                'label': gettext('Allowed Devices'),
                'tooltip': gettext(
                    'If empty, any kind of device compatible with this transport will be allowed. Else, only devices compatible with selected values will be allowed'
                ),
                'type': 'multichoice',
                'order': 102,
            },
        )
        field = self.addField(
            field,
            {
                'name': 'pools',
                'value': [],
                'values': [
                    {'id': x.uuid, 'text': x.name}
                    for x in ServicePool.objects.all().order_by('name')
                    if transport.protocol in x.service.getType().allowedProtocols  # type: ignore
                ],
                'label': gettext('Service Pools'),
                'tooltip': gettext('Currently assigned services pools'),
                'type': 'multichoice',
                'order': 103,
            },
        )
        field = self.addField(
            field,
            {
                'name': 'label',
                'length': 32,
                'value': '',
                'label': gettext('Label'),
                'tooltip': gettext(
                    'Metapool transport label (only used on metapool transports grouping)'
                ),
                'type': 'text',
                'order': 201,
                'tab': gettext(gui.ADVANCED_TAB),
            },
        )

        return field

    def item_as_dict(self, item: Transport) -> typing.Dict[str, typing.Any]:
        type_ = item.getType()
        pools = [{'id': x.uuid} for x in item.deployedServices.all()]
        return {
            'id': item.uuid,
            'name': item.name,
            'tags': [tag.tag for tag in item.tags.all()],
            'comments': item.comments,
            'priority': item.priority,
            'nets_positive': item.nets_positive,
            'label': item.label,
            'networks': [{'id': n.uuid} for n in item.networks.all()],
            'allowed_oss': [{'id': x} for x in item.allowed_oss.split(',')]
            if item.allowed_oss != ''
            else [],
            'pools': pools,
            'pools_count': len(pools),
            'deployed_count': item.deployedServices.count(),
            'type': type_.type(),
            'type_name': type_.name(),
            'protocol': type_.protocol,
            'permission': permissions.getEffectivePermission(self._user, item),
        }

    def beforeSave(self, fields: typing.Dict[str, typing.Any]) -> None:
        fields['allowed_oss'] = ','.join(fields['allowed_oss'])
        # If label has spaces, replace them with underscores
        fields['label'] = fields['label'].strip().replace(' ', '-')
        # And ensure small_name chars are valid [ a-zA-Z0-9:-]+
        if fields['label'] and not re.match(r'^[a-zA-Z0-9:-]+$', fields['label']):
            raise self.invalidRequestException(
                _('Label must contain only letters, numbers, ":" and "-"')
            )

    def afterSave(self, item: Transport) -> None:
        try:
            networks = self._params['networks']
        except Exception:  # No networks passed in, this is ok
            logger.debug('No networks')
            return
        if networks is None:
            return
        logger.debug('Networks: %s', networks)
        item.networks.set(Network.objects.filter(uuid__in=networks))  # type: ignore  # set is not part of "queryset"

        try:
            pools = self._params['pools']
        except Exception:
            logger.debug('No pools')
            pools = None

        if pools is None:
            return

        logger.debug('Pools: %s', pools)
        item.deployedServices.set(ServicePool.objects.filter(uuid__in=pools))  # type: ignore  # set is not part of "queryset"

        # try:
        #    oss = ','.join(self._params['allowed_oss'])
        # except:
        #    oss = ''
        # logger.debug('Devices: {0}'.format(oss))
        # item.allowed_oss = oss
        # item.save()  # Store correctly the allowed_oss
