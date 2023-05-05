# -*- coding: utf-8 -*-

#
# Copyright (c) 2014-2019 Virtual Cable S.L.
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
@itemor: Adolfo Gómez, dkmaster at dkmon dot com
"""
import logging
import typing

from django.utils.translation import gettext_lazy as _, gettext

from uds.models import Network
from uds.core.util import net
from uds.core.util import permissions
from uds.core.ui import gui

from uds.REST.model import ModelHandler, SaveException

logger = logging.getLogger(__name__)

# Enclosed methods under /item path


class Networks(ModelHandler):
    """
    Processes REST requests about networks
    Implements specific handling for network related requests using GUI
    """

    model = Network
    save_fields = ['name', 'net_string', 'tags']

    table_title = _('Networks')
    table_fields = [
        {
            'name': {
                'title': _('Name'),
                'visible': True,
                'type': 'icon',
                'icon': 'fa fa-globe text-success',
            }
        },
        {'net_string': {'title': _('Range')}},
        {'networks_count': {'title': _('Used by'), 'type': 'numeric', 'width': '8em'}},
        {'tags': {'title': _('tags'), 'visible': False}},
    ]

    def beforeSave(self, fields: typing.Dict[str, typing.Any]) -> None:
        logger.debug('Before %s', fields)
        try:
            nr = net.networkFromString(fields['net_string'])
            fields['net_start'] = nr[0]
            fields['net_end'] = nr[1]
        except Exception as e:
            raise SaveException(gettext('Invalid network: {}').format(e))
        logger.debug('Processed %s', fields)

    def getGui(self, type_: str) -> typing.List[typing.Any]:
        return self.addField(
            self.addDefaultFields([], ['name', 'tags']),
            {
                'name': 'net_string',
                'value': '',
                'label': gettext('Network range'),
                'tooltip': gettext(
                    'Network range. Accepts most network definitions formats (range, subnet, host, etc...'
                ),
                'type': gui.InputField.TEXT_TYPE,
                'order': 100,  # At end
            },
        )

    def item_as_dict(self, item: Network) -> typing.Dict[str, typing.Any]:
        return {
            'id': item.uuid,
            'name': item.name,
            'tags': [tag.tag for tag in item.tags.all()],
            'net_string': item.net_string,
            'networks_count': item.transports.count(),
            'permission': permissions.getEffectivePermission(self._user, item),
        }
