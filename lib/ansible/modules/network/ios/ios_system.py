#!/usr/bin/python
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#

ANSIBLE_METADATA = {
    'status': ['preview'],
    'supported_by': 'core',
    'version': '1.0'
}

DOCUMENTATION = """
---
module: ios_system
version_added: "2.3"
author: "Peter Sprygada (@privateip)"
short_description: Manage the system attributes on Cisco IOS devices
description:
  - This module provides declarative management of node system attributes
    on Cisco IOS devices.  It provides an option to configure host system
    parameters or remove those parameters from the device active
    configuration.
options:
  hostname:
    description:
      - The C(hostname) argument will configure the device hostname
        parameter on Cisco IOS devices.  The C(hostname) value is an
        ASCII string value.
    required: false
    default: null
  domain_name:
    description:
      - The C(description) argument will configure the IP domain name
        on the remote device to the provided value.  The C(domain_name)
        argument should be in the dotted name form and will be
        appended to the C(hostname) to create a fully-qualified
        domain name
    required: false
    default: null
  domain_search:
    description:
      - The C(domain_list) provides the list of domain suffixes to
        append to the hostname for the purpose of doing name resolution.
        This argument accepts a list of names and will be reconciled
        with the current active configuration on the running node.
    required: false
    default: null
  lookup_source:
    description:
      - The C(lookup_source) argument provides one or more source
        interfaces to use for performing DNS lookups.  The interface
        provided in C(lookup_source) must be a valid interface configured
        on the device.
    required: false
    default: null
  lookup_enabled:
    description:
      - The C(lookup_enabled) argument provides administrative control
        for enabling or disabling DNS lookups.  When this argument is
        set to True, lookups are performed and when it is set to False,
        lookups are not performed.
    required: false
    default: null
    choices: ['true', 'false']
  name_servers:
    description:
      - The C(name_serves) argument accepts a list of DNS name servers by
        way of either FQDN or IP address to use to perform name resolution
        lookups.  This argument accepts wither a list of DNS servers See
        examples.
    required: false
    default: null
  state:
    description:
      - The C(state) argument configures the state of the configuration
        values in the device's current active configuration.  When set
        to I(present), the values should be configured in the device active
        configuration and when set to I(absent) the values should not be
        in the device active configuration
    required: false
    default: present
    choices: ['present', 'absent']
"""

EXAMPLES = """
- name: configure hostname and domain name
  ios_system:
    hostname: ios01
    domain_name: eng.ansible.com
    domain-search:
      - ansible.com
      - redhat.com
      - cisco.com
- name: remove configuration
  ios_system:
    state: absent
- name: configure DNS lookup sources
  ios_system:
    lookup_source: MgmtEth0/0/CPU0/0
    lookup_enabled: yes
- name: configure name servers
  ios_system:
    name_servers:
      - 8.8.8.8
      - 8.8.4.4
"""

RETURN = """
commands:
  description: The list of configuration mode commands to send to the device
  returned: always
  type: list
  sample:
    - hostname ios01
    - ip domain name eng.ansible.com
start:
  description: The time the job started
  returned: always
  type: str
  sample: "2016-11-16 10:38:15.126146"
end:
  description: The time the job ended
  returned: always
  type: str
  sample: "2016-11-16 10:38:25.595612"
delta:
  description: The time elapsed to perform all operations
  returned: always
  type: str
  sample: "0:00:10.469466"
"""
import re

from ansible.module_utils.local import LocalAnsibleModule
from ansible.module_utils.ios import get_config, load_config
from ansible.module_utils.network_common import ComplexList

_CONFIGURED_VRFS = None

def has_vrf(module, vrf):
    global _CONFIGURED_VRFS
    if _CONFIGURED_VRFS is not None:
        return vrf in _CONFIGURED_VRFS
    config = get_config(module)
    _CONFIGURED_VRFS = re.findall('vrf definition (\S+)', config)
    return vrf in _CONFIGURED_VRFS

def requires_vrf(module, vrf):
    if not has_vrf(module, vrf):
        module.fail_json(msg='vrf %s is not configured' % vrf)

def diff_list(want, have):
    adds = [w for w in want if w not in have]
    removes = [h for h in have if h not in want]
    return (adds, removes)

def map_obj_to_commands(want, have, module):
    commands = list()
    state = module.params['state']

    needs_update = lambda x: want.get(x) and (want.get(x) != have.get(x))

    if state == 'absent':
        if have['hostname'] != 'Router':
            commands.append('no hostname')

        if have['lookup_source']:
            commands.append('no ip domain lookup source-interface %s' % have['lookup_source'])

        if have['lookup_enabled'] is False:
            commands.append('ip domain lookup')

        vrfs = set()
        for item in have['domain_name']:
            if item['vrf'] and item['vrf'] not in vrfs:
                vrfs.add(item['vrf'])
                commands.append('no ip domain name vrf %s' % item['vrf'])
            elif None not in vrfs:
                vrfs.add(None)
                commands.append('no ip domain name')

        vrfs = set()
        for item in have['domain_search']:
            if item['vrf'] and item['vrf'] not in vrfs:
                vrfs.add(item['vrf'])
                commands.append('no ip domain list vrf %s' % item['vrf'])
            elif None not in vrfs:
                vrfs.add(None)
                commands.append('no ip domain list')

        vrfs = set()
        for item in have['name_servers']:
            if item['vrf'] and item['vrf'] not in vrfs:
                vrfs.add(item['vrf'])
                commands.append('no ip name-server vrf %s' % item['vrf'])
            elif None not in vrfs:
                vrfs.add(None)
                commands.append('no ip name-server')

    elif state == 'present':
        if needs_update('hostname'):
            commands.append('hostname %s' % want['hostname'])

        if needs_update('lookup_source'):
            commands.append('ip domain lookup source-interface %s' % want['lookup_source'])

        if needs_update('lookup_enabled'):
            cmd = 'ip domain lookup'
            if want['lookup_enabled'] is False:
                cmd = 'no %s' % cmd
            commands.append(cmd)

        if want['domain_name']:
            adds, removes = diff_list(want['domain_name'], have['domain_name'])
            for item in removes:
                if item['vrf']:
                    commands.append('no ip domain name vrf %s %s' % (item['vrf'], item['name']))
                else:
                    commands.append('no ip domain name %s' % item['name'])
            for item in adds:
                if item['vrf']:
                    requires_vrf(module, item['vrf'])
                    commands.append('ip domain name vrf %s %s' % (item['vrf'], item['name']))
                else:
                    commands.append('ip domain name %s' % item['name'])

        if want['domain_search']:
            adds, removes = diff_list(want['domain_search'], have['domain_search'])
            for item in removes:
                if item['vrf']:
                    commands.append('no ip domain list vrf %s %s' % (item['vrf'], item['name']))
                else:
                    commands.append('no ip domain list %s' % item['name'])
            for item in adds:
                if item['vrf']:
                    requires_vrf(module, item['vrf'])
                    commands.append('ip domain list vrf %s %s' % (item['vrf'], item['name']))
                else:
                    commands.append('ip domain list %s' % item['name'])


        if want['name_servers']:
            adds, removes = diff_list(want['name_servers'], have['name_servers'])
            for item in removes:
                if item['vrf']:
                    commands.append('no ip name-server vrf %s %s' % (item['vrf'], item['server']))
                else:
                    commands.append('no ip name-server %s' % item['server'])
            for item in adds:
                if item['vrf']:
                    requires_vrf(module, item['vrf'])
                    commands.append('ip name-server vrf %s %s' % (item['vrf'], item['server']))
                else:
                    commands.append('ip name-server %s' % item['server'])

    return commands

def parse_hostname(config):
    match = re.search('^hostname (\S+)', config, re.M)
    return match.group(1)

def parse_domain_name(config):
    match = re.findall('^ip domain name (?:vrf (\S+) )*(\S+)', config, re.M)
    matches = list()
    for vrf, name in match:
        if not vrf:
            vrf = None
        matches.append({'name': name, 'vrf': vrf})
    return matches

def parse_domain_search(config):
    match = re.findall('^ip domain list (?:vrf (\S+) )*(\S+)', config, re.M)
    matches = list()
    for vrf, name in match:
        if not vrf:
            vrf = None
        matches.append({'name': name, 'vrf': vrf})
    return matches

def parse_name_servers(config):
    match = re.findall('^ip name-server (?:vrf (\S+) )*(\S+)', config, re.M)
    matches = list()
    for vrf, server in match:
        if not vrf:
            vrf = None
        matches.append({'server': server, 'vrf': vrf})
    return matches

def parse_lookup_source(config):
    match = re.search('ip domain lookup source-interface (\S+)', config, re.M)
    if match:
        return match.group(1)

def map_config_to_obj(module):
    config = get_config(module)
    return {
        'hostname': parse_hostname(config),
        'domain_name': parse_domain_name(config),
        'domain_search': parse_domain_search(config),
        'lookup_source': parse_lookup_source(config),
        'lookup_enabled': 'no ip domain lookup' not in config,
        'name_servers': parse_name_servers(config)
    }

def map_params_to_obj(module):
    obj = {
        'hostname': module.params['hostname'],
        'lookup_source': module.params['lookup_source'],
        'lookup_enabled': module.params['lookup_enabled'],
    }

    domain_name = ComplexList(dict(
        name=dict(key=True),
        vrf=dict()
    ))

    domain_search = ComplexList(dict(
        name=dict(key=True),
        vrf=dict()
    ))

    name_servers = ComplexList(dict(
        server=dict(key=True),
        vrf=dict()
    ))

    for arg, cast in [('domain_name', domain_name),
                      ('domain_search', domain_search),
                      ('name_servers', name_servers)]:

        if module.params[arg]:
            obj[arg] = cast(module.params[arg])
        else:
            obj[arg] = None

    return obj

def main():
    """ Main entry point for Ansible module execution
    """
    argument_spec = dict(
        hostname=dict(),

        domain_name=dict(type='list'),
        domain_search=dict(type='list'),
        name_servers=dict(type='list'),

        lookup_source=dict(),
        lookup_enabled=dict(type='bool'),

        state=dict(choices=['present', 'absent'], default='present')
    )

    module = LocalAnsibleModule(argument_spec=argument_spec,
                                supports_check_mode=True)

    result = {'changed': False}

    want = map_params_to_obj(module)
    have = map_config_to_obj(module)

    commands = map_obj_to_commands(want, have, module)
    result['commands'] = commands

    if commands:
        if not module.check_mode:
            load_config(module, commands)
        result['changed'] = True

    module.exit_json(**result)

if __name__ == "__main__":
    main()
