# -*- coding: utf-8 -*-
#
# Copyright (c) 2013-2020 Virtual Cable S.L.U.
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
import datetime
import logging
import typing

from django.utils.translation import gettext_lazy as _

from uds.core.managers.stats import StatsManager
from uds.models import NEVER, Provider, Service, ServicePool, Authenticator


logger = logging.getLogger(__name__)

CounterClass = typing.TypeVar(
    'CounterClass', Provider, Service, ServicePool, Authenticator
)

# Posible counters, note that not all are used by every posible type
# FIRST_COUNTER_TYPE, LAST_COUNTER_TYPE are just a placeholder for sanity checks
(
    CT_LOAD,
    CT_STORAGE,
    CT_ASSIGNED,
    CT_INUSE,
    CT_AUTH_USERS,
    CT_AUTH_USERS_WITH_SERVICES,
    CT_AUTH_SERVICES,
    CT_CACHED,
) = range(8)

__caRead: typing.Dict = {}
__caWrite: typing.Dict = {}
__transDict: typing.Dict = {}
__typeTitles: typing.Dict = {}


def addCounter(
    obj: CounterClass,
    counterType: int,
    counterValue: int,
    stamp: typing.Optional[datetime.datetime] = None,
) -> bool:
    """
    Adds a counter stat to specified object

    Although any counter type can be added to any object, there is a relation that must be observed
    or, otherway, the stats will not be recoverable at all:


    note: Runtime checks are done so if we try to insert an unssuported stat, this won't be inserted and it will be logged
    """
    type_ = type(obj)
    if type_ not in __caWrite.get(counterType, ()):  # pylint: disable
        logger.error(
            'Type %s does not accepts counter of type %s',
            type_,
            counterValue,
            exc_info=True,
        )
        return False

    return StatsManager.manager().addCounter(
        __transDict[type(obj)], obj.id, counterType, counterValue, stamp
    )


def getCounters(
    obj: CounterClass, counterType: int, **kwargs
) -> typing.Generator[typing.Tuple[datetime.datetime, int], None, None]:
    """
    Get counters

    Args:
        obj: Obj for which to recover stats counters
        counterType: type of counter to recover
        since: (optional, defaults to 'Since beginning') Start date for counters to recover
        to: (optional, defaults to 'Until end') En date for counter to recover
        limit: (optional, defaults to 1000) Number of counter to recover. This is an 'At most' advice. The returned number of value
               can be lower, or even 1 more than requested due to a division for retrieving object at database

    Returns:
        A generator, that contains pairs of (stamp, value) tuples
    """
    since = kwargs.get('since') or NEVER
    to = kwargs.get('to') or datetime.datetime.now()
    limit = kwargs.get('limit')
    use_max = kwargs.get('use_max', False)
    type_ = type(obj)

    readFncTbl = __caRead.get(type_)

    if not readFncTbl:
        logger.error('Type %s has no registered stats', type_)
        return

    fnc = readFncTbl.get(counterType)

    if not fnc:
        logger.error('Type %s has no registerd stats of type %s', type_, counterType)
        return

    if not kwargs.get('all', False):
        owner_ids = fnc(obj)
    else:
        owner_ids = None

    for i in StatsManager.manager().getCounters(
        __transDict[type(obj)],
        counterType,
        owner_ids,
        since,
        to,
        kwargs.get('interval'),
        kwargs.get('max_intervals'),
        limit,
        use_max,
    ):
        yield (datetime.datetime.fromtimestamp(i[0]), i[1])


def getCounterTitle(counterType: int) -> str:
    return __typeTitles.get(counterType, '').title()


# Data initialization
def _initializeData() -> None:
    """
    Initializes dictionaries.

    Hides data from global var space
    """

    __caWrite.update(
        {
            CT_LOAD: (Provider,),
            CT_STORAGE: (Service,),
            CT_ASSIGNED: (ServicePool,),
            CT_INUSE: (ServicePool,),
            CT_AUTH_USERS: (Authenticator,),
            CT_AUTH_SERVICES: (Authenticator,),
            CT_AUTH_USERS_WITH_SERVICES: (Authenticator,),
            CT_CACHED: (ServicePool,),
        }
    )

    # OBtain  ids from variups type of object to retrieve stats
    def get_Id(obj):
        return obj.id

    def get_P_S_Ids(provider) -> typing.Tuple:
        return tuple(i.id for i in provider.services.all())

    def get_S_DS_Ids(service) -> typing.Tuple:
        return tuple(i.id for i in service.deployedServices.all())

    def get_P_S_DS_Ids(provider) -> typing.Tuple:
        res: typing.Tuple = ()
        for i in provider.services.all():
            res += get_S_DS_Ids(i)
        return res

    __caRead.update(
        {
            Provider: {
                CT_LOAD: get_Id,
                CT_STORAGE: get_P_S_Ids,
                CT_ASSIGNED: get_P_S_DS_Ids,
                CT_INUSE: get_P_S_DS_Ids,
            },
            Service: {
                CT_STORAGE: get_Id,
                CT_ASSIGNED: get_S_DS_Ids,
                CT_INUSE: get_S_DS_Ids,
            },
            ServicePool: {CT_ASSIGNED: get_Id, CT_INUSE: get_Id, CT_CACHED: get_Id},
            Authenticator: {
                CT_AUTH_USERS: get_Id,
                CT_AUTH_SERVICES: get_Id,
                CT_AUTH_USERS_WITH_SERVICES: get_Id,
            },
        }
    )

    def _getIds(obj) -> typing.Tuple:
        to = type(obj)

        if to is ServicePool or to is Authenticator:
            return to.id

        if to is Service:
            return tuple(i.id for i in obj.userServices.all())

        res: typing.Tuple = ()
        if to is Provider:
            for i in obj.services.all():
                res += _getIds(i)
            return res

        return ()

    OT_PROVIDER, OT_SERVICE, OT_DEPLOYED, OT_AUTHENTICATOR = range(4)

    # Dict to convert objects to owner types
    # Dict for translations
    __transDict.update(
        {
            ServicePool: OT_DEPLOYED,
            Service: OT_SERVICE,
            Provider: OT_PROVIDER,
            Authenticator: OT_AUTHENTICATOR,
        }
    )

    # Titles of types
    __typeTitles.update(
        {
            CT_ASSIGNED: _('Assigned'),
            CT_INUSE: _('In use'),
            CT_LOAD: _('Load'),
            CT_STORAGE: _('Storage'),
            CT_AUTH_USERS: _('Users'),
            CT_AUTH_USERS_WITH_SERVICES: _('Users with services'),
            CT_AUTH_SERVICES: _('User Services'),
            CT_CACHED: _('Cached'),
        }
    )


_initializeData()
