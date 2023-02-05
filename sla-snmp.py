#!/usr/bin/env python3

import logging
import sys
from argparse import ArgumentParser, Action, OPTIONAL
from subprocess import Popen, PIPE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

rttMonCtrlAdminTag = "iso.3.6.1.4.1.9.9.42.1.2.1.1.3"
rttMonCtrlAdminStatus = "iso.3.6.1.4.1.9.9.42.1.2.1.1.9"
rttActive = 1
snmpOpts = "-OQ"


def get_args():
    parser = ArgumentParser(description='Get data from ALS')
    grps = parser.add_argument_group('Server')
    grps.add_argument('--server', required=True, action='store', help='SLA server')
    grps.add_argument('--server-port', action='store', help='Server port', default=161)
    grps.add_argument('--server-snmp-version', action='store', help='Server SNMP version', default="2c")
    grps.add_argument('--server-read-community', action='store',
                      help='Server read community', default='public')
    grps.add_argument('--tag', required=True, action='store', help='SLA tag')
    grpc = parser.add_argument_group('Client')
    grpc.add_argument('--client', required=True, action='store', help='Client IP')
    grpc.add_argument('--client-port', action='store', help='Client port', default=161)
    grpc.add_argument('--client-snmp-version', action='store', help='Client SNMP version', default="2c")
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
                t = 'i'
            else:
                t = 's'
        else:
            oid, t, val = values
        
        items = getattr(namespace, self.dest, None)
        items = _copy_items(items)
        items.append({'oid': oid, 'type': t, 'value': val})
        setattr(namespace, self.dest, items)


def parse_snmp_data(data):
    result = {}
    for line in data.splitlines():
        if line.startswith('iso'):
            oid, value = line.split(' = ')
            result[oid] = eval(value)
    return result


def get_snmp_index(oid):
    return oid.split('.')[-1]


def get_snmp_data(args, oids, server='server'):
    p = Popen(["snmpget", snmpOpts,
               f"-v{getattr(args, f'{server}_snmp_version')}",
               f"-c{getattr(args, f'{server}_read_community')}",
               f"{getattr(args, f'{server}')}:{getattr(args, f'{server}_port')}"] + oids,
              stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    if p.wait() != 0:
        logger.error(f"Error: {stderr}")
        sys.exit(1)
    return stdout.decode('utf-8')


def set_snmp_data(args, oids, server='server'):
    p = Popen(["snmpset", snmpOpts,
               f"-v{getattr(args, f'{server}_snmp_version')}",
               f"-c{getattr(args, f'{server}_write_community')}",
               f"{getattr(args, f'{server}')}:{getattr(args, f'{server}_port')}"] +
              [value for oid in oids for value in oid.values()],
              stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    if p.wait() != 0:
        logger.error(f"Error: {stderr}")
        sys.exit(1)
    return stdout.decode('utf-8')


def get_snmp_data_table(args, oids, server='server'):
    p = Popen(["snmpbulkwalk", snmpOpts,
               f"-v{getattr(args, f'{server}_snmp_version')}",
               f"-c{getattr(args, f'{server}_read_community')}",
               f"{getattr(args, f'{server}')}:{getattr(args, f'{server}_port')}"] + oids,
              stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    if p.wait() != 0:
        logger.error(f"Error: {stderr}")
        sys.exit(1)
    return stdout.decode('utf-8')


def compare_snmp_data(oids, varBinds):
    """Compare SNMP data with expected values, return True if all values are equal"""
    equal = True
    for oid in oids:
        if oid['type'] == 'i':
            if varBinds[oid['oid']] != int(oid['value']):
                logger.error(
                    f"OID {oid['oid']} value {varBinds[oid['oid']]} is not equal to {oid['value']}")
                equal = False
        elif oid['type'] == 's':
            if varBinds[oid['oid']] != oid['value']:
                logger.error(
                    f"OID {oid['oid']} value {varBinds[oid['oid']]} is not equal to {oid['value']}")
                equal = False
    return equal


def main(args):
    logger.info('Get data from server')
    varBindsRttTag = parse_snmp_data(get_snmp_data_table(args, [rttMonCtrlAdminTag], 'server'))
    logger.debug(f"rttMonCtrlAdminTag: {varBindsRttTag}")
    for oid, value in varBindsRttTag.items():
        if value == args.tag:
            logger.info(f"Found tag {args.tag} in {oid}")
            rttIndex = get_snmp_index(oid)
            varBindsRttStatus = parse_snmp_data(get_snmp_data(args, [f"{rttMonCtrlAdminStatus}.{rttIndex}"], 'server'))
            logger.debug(f"rttMonCtrlAdminStatus: {varBindsRttStatus}")
            if varBindsRttStatus[f"{rttMonCtrlAdminStatus}.{rttIndex}"] == rttActive:
                varBindsClient = parse_snmp_data(get_snmp_data(args, [oid['oid'] for oid in args.oid_ok], 'client'))
                logger.debug(f"RTT status is OK, Client data: {varBindsClient}")
                if not compare_snmp_data(args.oid_ok, varBindsClient):
                    logger.info('RTT status is OK, Update client data')
                    varBindsClientUpdate = set_snmp_data(args, args.oid_ok, 'client')
                    logger.debug(f"Client data update: {varBindsClientUpdate}")
                    if not compare_snmp_data(args.oid_ok, varBindsClientUpdate):
                        logger.error('Update client data failed')
                        sys.exit(1)
            else:
                varBindsClient = parse_snmp_data(get_snmp_data(args, [oid['oid'] for oid in args.oid_fail], 'client'))
                logger.debug(f"RTT status is FAIL, Client data: {varBindsClient}")
                if not compare_snmp_data(args.oid_fail, varBindsClient):
                    logger.info('RTT status is FAIL, Update client data')
                    set_snmp_data(args, args.oid_fail, 'client')
                    varBindsClientUpdate = set_snmp_data(args, args.oid_fail, 'client')
                    logger.debug(f"Client data update: {varBindsClientUpdate}")
                    if not compare_snmp_data(args.oid_fail, varBindsClientUpdate):
                        logger.error('Update client data failed')
                        sys.exit(1)
            break


if __name__ == '__main__':
    """ SLA SNMP"""
    # ch = logging.StreamHandler(sys.stdout)
    # logger.addHandler(ch)
    logger.default_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    arguments = get_args()
    
    if arguments.log:
        fh = logging.FileHandler(arguments.log)
        logger.addHandler(fh)
    if arguments.verbose:
        logger.setLevel(logging.DEBUG)
    
    logger.info('Start')
    main(arguments)
