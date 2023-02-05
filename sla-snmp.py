#!/usr/bin/env python3

import logging
import sys
from argparse import ArgumentParser, Action, OPTIONAL
from subprocess import Popen, PIPE

logger = logging.getLogger(__name__)

rttMonCtrlAdminTag = "iso.3.6.1.4.1.9.9.42.1.2.1.1.3"
rttMonLatestRttOperSense = "iso.3.6.1.4.1.9.9.42.1.2.10.1.2"
rttResponseSense = [
    "Other",
    "Ok",
    "Disconnected",
    "Over Threshold",
    "Timeout",
    "Busy",
    "Not Connected",
    "Dropped",
    "Sequence Error",
    "Verify Error",
    "Application Specific",
    "DNS Server Timeout",
    "TCP Connect Timeout",
    "HTTP Transaction Timeout",
    "DNS Query Error",
    "HTTP Error",
    "Error",
    "MPLS Lsp Echo Tx Error",
    "MPLS Lsp Unreachable",
    "MPLS Lsp Malformed Req",
    "MPLS Lsp Reach but Not FEC",
    "Enable Ok",
    "Enable No Connect",
    "Enable Version Fail",
    "Enable Internal Error",
    "Enable Abort",
    "Enable Fail",
    "Enable AuthFail",
    "Enable Format Error",
    "Enable Port in Use",
    "Stats Retrieve Ok",
    "Stats Retrieve No Connect",
    "Stats Retrieve Version Fail",
    "Stats Retrieve Internal Error",
    "Stats Retrieve Abort",
    "Stats Retrieve Fail",
    "Stats Retrieve Auth Fail",
    "Stats Retrieve Format Error",
    "Stats Retrieve Port in Use"
]
rttResponseOk = 1
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
    return parse_snmp_data(stdout.decode('utf-8'))


def set_snmp_data(args, oids, server='server'):
    logger.debug(f"set_snmp_data: {getattr(args, f'{server}')}, {[value for oid in oids for value in oid.values()]}")
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
    return parse_snmp_data(stdout.decode('utf-8'))


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
    return parse_snmp_data(stdout.decode('utf-8'))


def compare_snmp_data(oids, varBinds):
    """Compare SNMP data with expected values, return True if all values are equal"""
    equal = True
    for oid in oids:
        if oid['type'] == 'i':
            if varBinds[oid['oid']] != int(oid['value']):
                logger.warning(
                    f"OID {oid['oid']} value {varBinds[oid['oid']]} is not equal to {oid['value']}")
                equal = False
        elif oid['type'] == 's':
            if varBinds[oid['oid']] != oid['value']:
                logger.warning(
                    f"OID {oid['oid']} value {varBinds[oid['oid']]} is not equal to {oid['value']}")
                equal = False
    return equal


def main(args):
    logger.debug(f'Get data from server {args.server}')
    varBindsRttTag = get_snmp_data_table(args, [rttMonCtrlAdminTag], 'server')
    logger.debug(f"Server: rttMonCtrlAdminTags: {varBindsRttTag}")
    for oid, value in varBindsRttTag.items():
        if value == args.tag:
            logger.debug(f"Found tag {args.tag} in {oid}")
            rttIndex = get_snmp_index(oid)
            varBindsRttStatus = get_snmp_data(args, [f"{rttMonLatestRttOperSense}.{rttIndex}"], 'server')
            logger.debug(f"rttMonCtrlAdminStatus: {varBindsRttStatus}")
            logger.info(
                f"Server {args.server} RTT: '{args.tag}' status is "
                f"{rttResponseSense[varBindsRttStatus[f'{rttMonLatestRttOperSense}.{rttIndex}']]} "
                f"({varBindsRttStatus[f'{rttMonLatestRttOperSense}.{rttIndex}']})")
            if varBindsRttStatus[f"{rttMonLatestRttOperSense}.{rttIndex}"] == rttResponseOk:
                varBindsClient = get_snmp_data(args, [oid['oid'] for oid in args.oid_ok], 'client')
                logger.debug(f"RTT status is OK, Client data: {varBindsClient}")
                if not compare_snmp_data(args.oid_ok, varBindsClient):
                    logger.info('RTT status is OK, Update client data')
                    varBindsClientUpdate = set_snmp_data(args, args.oid_ok, 'client')
                    logger.debug(f"Client data update: {varBindsClientUpdate}")
                    if not compare_snmp_data(args.oid_ok, varBindsClientUpdate):
                        logger.error('Update client data failed')
                        sys.exit(1)
            else:
                varBindsClient = get_snmp_data(args, [oid['oid'] for oid in args.oid_fail], 'client')
                logger.debug(f"RTT status is FAIL, Client data: {varBindsClient}")
                if not compare_snmp_data(args.oid_fail, varBindsClient):
                    logger.info('RTT status is FAIL, Update client data')
                    varBindsClientUpdate = set_snmp_data(args, args.oid_fail, 'client')
                    logger.debug(f"Client data update: {varBindsClientUpdate}")
                    if not compare_snmp_data(args.oid_fail, varBindsClientUpdate):
                        logger.error('Update client data failed')
                        sys.exit(1)
            break


if __name__ == '__main__':
    """ SLA SNMP"""
    
    fm = logging.Formatter('%(levelname)s: %(message)s')
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fm)
    logger.addHandler(sh)
    
    arguments = get_args()
    
    if arguments.log:
        fm = logging.Formatter('%(asctime)s %(funcName)s :%(levelname)s: %(message)s')
        fh = logging.FileHandler(arguments.log)
        fh.setFormatter(fm)
        logger.addHandler(fh)
    if arguments.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    
    logger.debug('Start')
    main(arguments)
    logger.debug('Finish')
