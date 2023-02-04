#!/usr/bin/env python3

import logging
import sys
from argparse import ArgumentParser, Action, OPTIONAL

from pysnmp.hlapi import *
from pysnmp.entity.rfc3413.oneliner import cmdgen

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

rttMonCtrlAdminTag = ".1.3.6.1.4.1.9.9.42.1.2.1.1.3"
rttMonCtrlAdminStatus = ".1.3.6.1.4.1.9.9.42.1.2.1.1.9"
rttActive = "1"


def get_args():
    parser = ArgumentParser(description='Get data from ALS')
    grps = parser.add_argument_group('Server')
    grps.add_argument('--server', required=True, action='store', help='SLA server')
    grps.add_argument('--server-port', action='store', help='Server port', default=161)
    grps.add_argument('--server-read-community', action='store',
                      help='Server read community', default='public')
    grps.add_argument('--tag', required=True, action='store', help='SLA tag')
    grpc = parser.add_argument_group('Client')
    grpc.add_argument('--client', required=True, action='store', help='Client IP')
    grpc.add_argument('--client-port', action='store', help='Client port', default=161)
    grpc.add_argument('--client-read-community', action='store',
                      help='Client read community', default='public')
    grpc.add_argument('--client-write-community', action='store',
                      help='Client write community', default='private')
    grpc.add_argument('--oid-ok', required=True, action=_AppendOid, help='oid for OK status (oid:type:value)')
    grpc.add_argument('--oid-fail', required=True, action=_AppendOid, help='oid for FAIL status')
    grpl = parser.add_argument_group('Logging')
    grpl.add_argument('-v', '--verbose', action='store_true', help='Verbose')
    grpl.add_argument('-l', '--log', action='store', help='Log file', default="/tmp/sla-snmp.log")
    return parser.parse_args()


def _copy_items(items):
    if items is None:
        return []
    # The copy module is used only in the 'append' and 'append_const'
    # actions, and it is needed only when the default value isn't a list.
    # Delay its import for speeding up the common case.
    if type(items) is list:
        return items[:]
    import copy
    return copy.copy(items)


class _AppendOid(Action):
    
    def __init__(self,
                 option_strings,
                 dest,
                 nargs=None,
                 const=None,
                 default=None,
                 type=None,
                 choices=None,
                 required=False,
                 help=None,
                 metavar=None):
        if nargs == 0:
            raise ValueError('nargs for append actions must be != 0; if arg '
                             'strings are not supplying the value to append, '
                             'the append const action may be more appropriate')
        if const is not None and nargs != OPTIONAL:
            raise ValueError('nargs must be %r to supply const' % OPTIONAL)
        super(_AppendOid, self).__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=nargs,
            const=const,
            default=default,
            type=type,
            choices=choices,
            required=required,
            help=help,
            metavar=metavar)
    
    def __call__(self, parser, namespace, values, option_string=None):
        values = values.split(':')
        if len(values) < 2:
            raise ValueError('oid must be in format oid:type:value')
        elif len(values) == 2:
            oid, val = values
            if val.isdigit():
                t = 'I'
            else:
                t = 'S'
        else:
            oid, t, val = values
        
        items = getattr(namespace, self.dest, None)
        items = _copy_items(items)
        items.append({'oid': oid, 'type': t, 'value': val})
        setattr(namespace, self.dest, items)


def get_snmp_data(host, port, community, oid):
    errorIndication, errorStatus, errorIndex, varBinds = next(
        getCmd(SnmpEngine(),
               CommunityData(community),
               UdpTransportTarget((host, port)),
               ContextData(),
               ObjectType(ObjectIdentity(oid)))
    )
    
    if errorIndication:
        print(errorIndication)
    elif errorStatus:
        print('%s at %s' % (
            errorStatus.prettyPrint(),
            errorIndex and varBinds[int(errorIndex) - 1][0] or '?'
        ))
    else:
        for varBind in varBinds:
            return varBind[1]

            
def get_snmp_data_table(host, port, community, oid):
    errorIndication, errorStatus, errorIndex, varBinds = next(
        nextCmd(SnmpEngine(),
                CommunityData(community),
                UdpTransportTarget((host, port)),
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
                lexicographicMode=False)
    )
    
    if errorIndication:
        logger.error(errorIndication)
    elif errorStatus:
        logger.error('%s at %s' % (
            errorStatus.prettyPrint(),
            errorIndex and varBinds[int(errorIndex) - 1][0] or '?'
        ))
    else:
        for varBind in varBinds:
            print(' = '.join([x.prettyPrint() for x in varBind]))
        return varBinds


def main(args):
    logger.info('Get data from server')
    server_data = get_snmp_data_table(args.server, args.server_port, args.server_read_community, rttMonCtrlAdminTag)
    test_data = get_snmp_data(args.server, args.server_port, args.server_read_community, ".1.3.6.1.4.1.9.9.42.1.2.1.1.3.50")
    for varBind in server_data:
        print(' = '.join([x.prettyPrint() for x in varBind]))
    logger.debug('Server data: %s', server_data)


if __name__ == '__main__':
    """ SLA SNMP"""
    ch = logging.StreamHandler(sys.stdout)
    logger.addHandler(ch)
    logger.default_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    arguments = get_args()

    if arguments.log:
        fh = logging.FileHandler(arguments.log)
        logger.addHandler(fh)
    if arguments.verbose:
        logger.setLevel(logging.DEBUG)
    
    logger.info('Start')
    main(arguments)
