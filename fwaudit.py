#!/usr/bin/env python2
# -*- coding: UTF-8 -*-
# vim: set expandtab sw=4 :

'''
Firmware Audit
Copyright (C) 2017-2018 PreOS Security Inc.
All Rights Reserved.

This code is licensed using GPLv2, see LICENSE.txt.

Firmware Audit is a firmware analysis tool which calls multiple tools
(eg, CHIPSEC, FWTS, etc.) and gathers the results for forensic analysis.

For more information, see README.txt.

This release is not yet feature complete, but is usable.
'''

# Check file size against max buffer before opening/reading. Disallow large files until buffering logic added.
# After initial creation of dir, don't keep updating owner/group/file-mode each run, only do that once.
# Fix list/dict issues with get_tool_arg()/set_tool_arg(). Simplify by removing 'args' dict, and putting args one level higher.
# Test sidecar hash file format against sha256sum tool.
# Understand how to properly set single GID from list, especially macOS non-POSIX behavior. Test sudo use with a user account and/or a root account that has multiple group memberships, including >16.
# Test sidecar hash files and manifest using sha26sum
# Fix manifest, dealing with path names, not just same-directory filenames, in a manifest file, such that sha256sum tool can verify it, so they can be used at PRD level, not just PTD level.
# Standardize use of return codes, int -vs- bool, some overwrite,
#     raise LookupError('msg')
#     status = os.EX_(OK, USAGE, DATAERROR, NOINPUT, NOTFOUND, NOPERM)
# Standardize use of output formatting, esp in large output templates
#    form = '{0:0.3d} xxx {1:0.2f}'; print(form.format(d,f))
#    form = '''...{foo} ... {bar} ...'''; #print(form.format(foo='x', bar='y'))


from __future__ import print_function
from __future__ import division
from __future__ import unicode_literals
# XXX add floating point

import sys
import os
import subprocess
import argparse
import platform
import hashlib
import base64
import textwrap
import uuid
import ctypes
import site
import time
import errno
import stat
import pwd
import grp
import getpass

EVENTLOG_AVAILABLE = True
try:
    import windows_eventlog  # XXX proper module name
except ImportError:
    EVENTLOG_AVAILABLE = False

SYSLOG_AVAILABLE = True
try:
    import syslog
except ImportError:
    SYSLOG_AVAILABLE = False

############################################################


# metadata.py
# Global variable: APP_METADATA

# XXX which of these are Python/PEP/PyPI standards?
__version__ = '0.0.4'
__status__ = 'PRE-ALPHA'
__author__ = 'PreOS Security Inc'
__copyright__ = 'Copyright 2017-2018, PreOS Security'
__credits__ = ['Lee Fisher', 'Paul English']
__maintainer__ = 'PreOS Security'
__email__ = 'fwaudit@preossec.com'
__license__ = 'GPL-2.0'
# __license__ = 'https://opensource.org/licenses/GPL-2.0'

APP_METADATA = {
    'home_page': '<https://preossec.com/products/fwaudit>',  # XXX create/test
    'copyright': '2017-2018',
    'short_name': 'fwaudit',
    'full_name': 'Firmware Audit (fwaudit)',
    'description': 'Platform firmware diagnostic tool.',
    'short_author': 'PreOS',
    'version': __version__ + '-' + __status__,
    'license': __license__,
    'contact': __email__,
    'full_author': __author__,
}

############################################################

# colors.py
# Global variable: COLORS
COLORS = {
    'RESET':       '\033[0m',  # '\033[0;0m' '\033[0m' '\033[00m' '\x1B[m'
    'NORMAL':      '\x1b[0m',
    'BOLD':        '\033[1m',  # '\033[01m'
    'REVERSE':     '\033[;7m',
    'FG_BLACK':    '\033[30m',
    'FG_RED':      '\033[31m',  # '\033[1;31m' '\033[91m' '\x1b[31m'
    'FG_GREEN':    '\033[32m',  # '\033[1;34m' '\033[94m'
    'FG_ORANGE':   '\033[33m',
    'FG_BLUE':     '\033[34m',  # '\033[0;32m' '\033[92m', '\x1b[32m'
    'FG_PURPLE':   '\033[35m',
    'FG_CYAN':     '\033[36m',  # '\033[1;36m'
    'FG_LT_GREY':  '\033[37m',
    'FG_DK_GREY':  '\033[90m',
    'FG_LT_RED':   '\033[91m',
    'FG_LT_GREEN': '\033[92m',
    'FG_YELLOW':   '\033[93m',  # '\x1b[33m'
    'FG_LT_BLUE':  '\033[94m',
    'FG_PINK':     '\033[95m',  # '\x1b[35m'
    'FG_LT_CYAN':  '\033[96m',
    'BG_BLACK':    '\033[40m',
    'BG_RED':      '\033[41m',
    'BG_GREEN':    '\033[42m',
    'BG_ORANGE':   '\033[43m',
    'BG_BLUE':     '\033[44m',
    'BG_PURPLE':   '\033[45m',
    'BG_CYAN':     '\033[46m',
    'BG_LT_GREY':  '\033[47m'
}

# The foreground/background colors for the prefix (INFO/DEBUG/etc) and message
# for error/info/warn/log/debug output. None means colorless output.
COLOR_DEFAULTS = {
    # Errors: red on black
    'error_pre_fg': COLORS['REVERSE'] + COLORS['BOLD'] + COLORS['FG_LT_RED'],
    'error_pre_bg': COLORS['BG_BLACK'],
    'error_msg_fg': COLORS['BOLD'] + COLORS['FG_LT_RED'],
    'error_msg_bg': COLORS['BG_BLACK'],
    # Warnings: yellow/orange on black
    'warn_pre_fg':  COLORS['REVERSE'] + COLORS['BOLD'] + COLORS['FG_YELLOW'],
    'warn_pre_bg':  COLORS['BG_BLACK'],
    'warn_msg_fg':  COLORS['BOLD'] + COLORS['FG_ORANGE'],
    'warn_msf_bg':  COLORS['BG_BLACK'],
    # Info: green on black
    'info_pre_fg':  COLORS['FG_LT_GREEN'],
    'info_pre_bg':  COLORS['BG_BLACK'],
    'info_msg_fg':  COLORS['FG_GREEN'],
    'info_msg_bg':  COLORS['BG_BLACK'],
    # Debug: yellow on blue
    'debug_pre_fg': COLORS['FG_YELLOW'],
    'debug_pre_bg': COLORS['BG_PURPLE'],
    'debug_msg_fg': COLORS['FG_YELLOW'],
    'debug_msg_bg': COLORS['BG_BLUE'],
    # No colors
    'log_pre_fg':   None,
    'log_pre_bg':   None,
    'log_msg_fg':   None,
    'log_msg_bg':   None
}

############################################################

# state.py
# Global variable: app_state
# input from user: arguments that control program logic.
app_state = {
    'debug': False,  # --debug
    'verbose': False,  # --verbose
    'logfile': None,  # --logfile
    'syslog_mode': False,  # --syslog
    'eventlog_mode': False,  # --eventlog
    'diagnostic_mode': False,  # --diags
    'version_mode': False,  # --version
    'list_tools_mode': False,  # --list_tools
    'list_profiles_mode': False,  # --list_profiles
    'user_tools': None,  # --tool=<tool_name> (can specify >1)
    'user_profiles': None,  # --profile=<profile_name> (can specify >1)
    'new_profiles': None,  # --new_profile=<json_string>
    'no_profile': None,  # --no_profile
    'selected_profile': None,
    'max_profiles': '1000',
    'meta_profile': [],
    'zip_results': False,  # --zip_results
    'output_dir': None,  # --output_dir dir string  (aka 'PD')
    'output_dir_specified': False,  # user specifed explicit PD using --output_dir
    'per_run_directory': None,
    'colorize': False,  # --colorize
    'omit_pii': False,  # --omit_pii
    'output_mode': 'merged',  # --output_mode
    'hash_mode': True,  # --hash, --nohash
    'manifest_mode': True,  # --manifest, --nomanifest
    'tools_and_profiles': None,  # sum of all tools + profiles + new_profiles
    'timestamp': None,  # timestamp of run, used to create target dir
    'switchar': '-',  # OS switch character
    'max_buf': 50000,  # XXX add way to override. Proper value?
    'shell_script_redir_string': None,
    'sudo_based_usage': False,
}

############################################################

# tools.py
# XXX all FW_Type args
# XXX all IOMMU Engine args
# XXX user input validation
# XXX maybe use per-tool arg, and a valid toolns?

# Global variable: TOOLS
# TOOLS: a list of dicts describing available tools.
# User can run a single tool using '--profile <toolname>'.
# User can view list of available tools using '--list-tools'.
# Dict schema: { name:'x', tool:'x', desc:'x' }
# Name -- is more of a namespace of this variance of tool run.
# Tool -- is proper name of tool.
# Desc -- is description of tool.
# mode -- mode of tool, valid modes: ('all', 'live', 'offline')
#         'all' means could be live or offline, used by get_version code.
# exrc -- expected_rc of tool.
# Args -- is list of tool options/arguments, and their defaults,
#         to be updated if user specifies new values on command line.
#
# For each a tool foo, there will be at leat 2 entries, one with
# name=foo_get_version and one with name=foo (or more specific
# name, like name=foo_rom_dump if using specific args beyond 'foo' use.

# Next step in refactoring:
# Separate TOOLS lists, one per-tool.
# Per-run code traverses multiple tools lists, or
# creates a single list from each tool's list.
#
# Next step after that:
# Template function that covers all code flow cases of all tools.
# Remove most of the tool code, one-function per namespace!
# One function for tags.
# One function for get_version and get_help.
# One function for native image tools, one for Python modules.

# Add command line args list from each function into struct
# Separate TOOLS structs, one per tool, in <toolname.py>, right above <toolname_resolver().

# Main needs way to determine which tools are installed/available, then build
# high-level tool list from each available tools's list.

# Add flag if native_spawn, python2_module, load, or other exec method.

# The current code that passes args to tools is ugly, commented out in M1.

# Need per-OS filenames, eg 'acpidump', 'acpidump.exe', 'acpidump.efi'.

TOOLS = [
    {
        'name': 'acpidump',
        'tool': 'acpidump',
        'desc': 'acpidump -z -b',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_bios_keyboard_buffer',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m common.bios_kbrd_buffer',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_bios_smi',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m common.bios_smi',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_bios_ts',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m common.bios_ts',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_bios_wp',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m common.bios_wp',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_ia32cfg',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m common.ia32cfg',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_memconfig',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m memconfig',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_remap',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m remap',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_rtclock',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m common.rtclock',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_secureboot_variables',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m common.secureboot.variables [-a modify]',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_smm',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m common.smm',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_smm_dma',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m smm_dma',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_smrr',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m common.smrr',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_spi_desc',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m common.spi_desc',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_spi_fdopss',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m common.spi_fdopss',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_spi_lock',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m common.spi_lock',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_uefi_access_spec',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m common.uefi.access_uefispec',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_test_uefi_s3_bootscript',
        'tool': 'chipsec_main',
        'desc': 'chipsec_main -m common.uefi.s3bootscript [-a <script_address>]',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
#    }, {
#        'name': 'chipsec_uefi_blacklist',
#        'tool': 'chipsec_main',
#        'desc': 'chipsec_main -i -n -m tools.uefi.blacklist -a uefi.rom,blacklist.json',
#        'mode': 'offline',
#        'exrc': 0,
#        'expected': [],
#        'actual': [],
#        'args': {
#            'rom_bin_file': 'rom.bin'}
    }, {
        'name': 'chipsec_acpi_list',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util acpi list',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_acpi_table',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util acpi table acpi_table.bin',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_cmos_dump',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util cmos dump',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_cpu_info',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util cpu info',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_cpu_pt',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util cpu pt',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
#    }, {
#        'name': 'chipsec_decode',
#        'tool': 'chipsec_util',
#        'desc': 'chipsec_util decode spi.bin',
#        'mode': 'offline',
#        'exrc': 0,
#        'expected': [],
#        'actual': [],
#        'args': {'chipsec_decode_fw_type': None}
    }, {
        'name': 'chipsec_decode_types',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util decode types',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_ec_dump',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util ec dump',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_io_list',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util io list',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
#    }, {
#        'name': 'chipsec_iommu_config',
#        'tool': 'chipsec_util',
#        'desc': 'chipsec_util iommu config',
#        'mode': 'live',
#        'exrc': 0,
#        'expected': [],
#        'actual': [],
#        'args': {'chipsec_iommu_engine': None}
    }, {
        'name': 'chipsec_iommu_list',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util iommu list',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_iommu_pt',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util iommu pt',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
#    }, {
#        'name': 'chipsec_iommu_status',
#        'tool': 'chipsec_util',
#        'desc': 'chipsec_util iommu status',
#        'mode': 'live',
#        'exrc': 0,
#        'expected': [],
#        'actual': [],
#        'args': {'chipsec_iommu_engine': None}
    }, {
        'name': 'chipsec_mmio_list',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util mmio list',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_pci_dump',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util pci dump',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_pci_enumerate',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util pci enumerate',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_pci_xrom',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util pci xrom',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_platform',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util platform',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_spd_detect',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util spd detect',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_spd_dump',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util spd dump',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_spidesc',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util spidesc spi.bin',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_spi_dump',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util spi dump rom.bin',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_spi_info',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util spi info',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_ucode_id',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util ucode id',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
#    }, {
#        'name': 'chipsec_uefi_decode',
#        'tool': 'chipsec_util',
#        'desc': 'chipsec_util uefi decode uefi.rom',
#        'mode': 'offline',
#        'exrc': 0,
#        'expected': [],
#        'actual': [],
#        'args': {'uefi_rom_bin_file': 'uefi.rom'}
    }, {
        'name': 'chipsec_uefi_keys',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util uefi keys uefi_keyvar.bin',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {},
    }, {
        'name': 'chipsec_uefi_nvram_auth',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util uefi nvram-auth rom.bin',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_uefi_nvram',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util uefi nvram rom.bin',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_uefi_s3_bootscript',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util uefi s3bootscript',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_uefi_tables',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util uefi tables',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_uefi_types',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util uefi types',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'chipsec_uefi_var_list',
        'tool': 'chipsec_util',
        'desc': 'chipsec_util uefi var-list',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'dmidecode_dump',
        'tool': 'dmidecode',
        'desc': 'Use DMIdecode to save data to dmidecode.bin',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
#    }, {
#        'name': 'dmidecode_decode',
#        'tool': 'dmidecode',
#        'desc': 'Use DMIdecode to view a previously-saved dmidecode.bin',
#        'mode': 'offline',
#        'exrc': 0,
#        'expected': [],
#        'actual': [],
#        'args': {'dmidecode_bin_file', 'dmidecode.bin'}
#    }, {
#        'name': 'flashrom_rom_dump',
#        'tool': 'flashrom',
#        'desc': 'FlashROM to dump platform ROM to rom.bin',
#        'mode': 'live',
#        'exrc': 0,
#        'expected': [],
#        'actual': [],
#        'args': {'rom_bin_file', 'rom.bin'}
    }, {
        'name': 'fwts_version',
        'tool': 'fwts',
        'desc': 'FWTS version',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'fwts_cpufreq',
        'tool': 'fwts',
        'desc': 'FWTS cpyfreq',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'fwts_maxfreq',
        'tool': 'fwts',
        'desc': 'FWTS maxfreq',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'fwts_msr',
        'tool': 'fwts',
        'desc': 'FWTS msr',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'fwts_mtrr',
        'tool': 'fwts',
        'desc': 'FWTS mtrr',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'fwts_nx',
        'tool': 'fwts',
        'desc': 'FWTS nx',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'fwts_virt',
        'tool': 'fwts',
        'desc': 'FWTS virt',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'fwts_aspm',
        'tool': 'fwts',
        'desc': 'FWTS aspm',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'fwts_dmicheck',
        'tool': 'fwts',
        'desc': 'FWTS dmicheck',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'fwts_apicedge',
        'tool': 'fwts',
        'desc': 'FWTS apicedge',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'fwts_klog',
        'tool': 'fwts',
        'desc': 'FWTS klog',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'fwts_oops',
        'tool': 'fwts',
        'desc': 'FWTS oops',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'fwts_esrt',
        'tool': 'fwts',
        'desc': 'FWTS esrt',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'fwts_acpi_tests',
        'tool': 'fwts',
        'desc': 'FWTS --acpi_tests',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'fwts_uefi_tests',
        'tool': 'fwts',
        'desc': 'FWTS --uefi_tests',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'intel_amt_discovery',
        'tool': 'INTEL-SA-00075-Discovery-Tool',
        'desc': 'INTEL-SA-00075-Discovery-Tool',
        'mode': 'live',
        'exrc': 254,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'intel_me_detection',
        'tool': 'intel_sa00086.py',
        'desc': 'INTEL-SA-00086-Detection-Tool',
        'mode': 'live',
        'exrc': 254,
        'expected': [],
        'actual': [],
        'args': {}
    }, {

        'name': 'lsusb',
        'tool': 'lsusb',
        'desc': 'lsusb -v -t',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'lshw',
        'tool': 'lshw',
        'desc': 'lshw -businfo -sanitize -notime',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'lspci_vvnn',
        'tool': 'lspci',
        'desc': 'lspci -vvnn',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
    }, {
        'name': 'lspci_xxx',
        'tool': 'lspci',
        'desc': 'lspci -xxx',
        'mode': 'live',
        'exrc': 0,
        'expected': [],
        'actual': [],
        'args': {}
 #   }, {
 #       'name': 'pawn',
 #       'tool': 'pawn',
 #       'desc': 'Google pawn to dump platform ROM to rom.bin',
 #       'mode': 'live',
 #       'exrc': 0,
 #       'expected': [],
 #       'actual': [],
 #       'args': {'rom_bin_file': 'rom.bin'}
    }
]

############################################################

# profiles.py
# Global variable: PROFILES
# PROFILES: a list of dicts describing available tool profiles.
# User can run a profile of tests via --profile <profilename>
# User can view list of available profiles using '--list_profiles'.
# Dict schema: { name:'x', desc:'x' tools:['x','x',x'] }
# Name is the name of the profile.
# Desc is description of profile.
# Tools is a list of tools used by this profile.
# XXX move into external file, JSON or INI.
# XXX CHIPSEC and FWTS suported tag lists, use proper subset

PROFILES = [
    {
        'name': 'rom_dump_chipsec',
        'desc': 'Live dump rom.bin using CHIPSEC.',
        'mode': 'live',
        'tools': ['chipsec_spi_dump']
    }, {
        'name': 'live_rom_dump_flashrom',
        'desc': 'Dump rom.bin using FlashROM.',
        'mode': 'live',
        'tools': ['flashrom_rom_dump']
    }, {
        'name': 'rom_dump_pawn',
        'desc': 'Dump rom.bin using Google Pawn.',
        'mode': 'live',
        'tools': ['pawn_rom_dump']
    }, {
        'name': 'live_acpi_dump_acpidump',
        'desc': 'Dump ACPI tables using acpidump.',
        'mode': 'live',
        'tools': ['acpidump']
    }, {
        'name': 'live_acpi_dump_chipsec',
        'desc': 'Dump ACPI tables using CHIPSEC.',
        'mode': 'live',
        'tools': ['chipsec_acpi_dump']
    }, {
        'name': 'live_acpi_dump_fwts',
        'desc': 'Dump ACPI tables using FWTS.',
        'mode': 'live',
        'tools': ['fwts_acpi_dump']
    }, {
        'name': 'fwts_recommended',
        'desc': 'Run all fwts recommended tests, each separately.',
        'mode': 'live',
        'tools': ['fwts_version',
                  'fwts_cpufreq',
                  'fwts_maxfreq',
                  'fwts_msr',
                  'fwts_mtrr',
                  'fwts_nx',
                  'fwts_virt',
                  'fwts_aspm',
                  'fwts_dmicheck',
                  'fwts_apicedge',
                  'fwts_klog',
                  'fwts_oops',
                  'fwts_esrt',
                  'fwts_uefi_tests']
    }, {
        'name': 'chipsec_all_security_tests',
        'desc': 'Run ALL chipsec_main security tests, each separately.',
        'mode': 'live',
        'tools': ['chipsec_test_bios_keyboard_buffer',
                  'chipsec_test_bios_smi',
                  'chipsec_test_bios_ts',
                  'chipsec_test_bios_wp',
                  'chipsec_test_ia32cfg',
                  'chipsec_test_memconfig',
                  'chipsec_test_remap',
                  'chipsec_test_rtclock',
                  'chipsec_test_secureboot_variables',
                  'chipsec_test_smm',
                  'chipsec_test_smm_dma',
                  'chipsec_test_smrr',
                  'chipsec_test_spi_desc',
                  'chipsec_test_spi_fdopss',
                  'chipsec_test_spi_lock',
                  'chipsec_test_uefi_access_spec']
    }
]

############################################################

# __main__.py


def main():
    '''The program main entry point, in addition to code at EOF.'''
    global app_state
    global TOOLS
    tool_status = 0  # XXX need to set during meta_profile run

    # Check if stdio redirected, remove colors?
    # Check if not a TTY?

    app_state['switchar'] = switch_character()
    parse_args()

    # The modes that display one thing and then exit.
    # Defer to argparse to handle the help/?/h options.
    if app_state['version_mode']:
        show_tool_version()  # --version
        return 0
    if app_state['diagnostic_mode']:
        show_diagnostics()  # --diags
        return 0
    if app_state['list_tools_mode']:
        list_tools()  # list_tools
        return 0
    if app_state['list_profiles_mode']:
        list_profiles()  # list_profiles
        return 0

    startup_message()

    if not supported_os():
        error('Unrecognized OS, cannot continue')
        # raise RuntimeError('unsupported operating system')
        # return os.OK  # USAGE NOINPUT NOTFOUND NOPERM
        return 1  # XXX generate exception

    if not supported_python():
        error('Invalid Python implementation')
        # raise RuntimeError('x')
        # return os.OK  # USAGE NOINPUT NOTFOUND NOPERM
        return 1  # XXX generate exception

    if (is_none_or_null(app_state['user_profiles']) and
       is_none_or_null(app_state['user_tools'])):
        error('No tool(s) or profile selected, use --tool or --profile.')
        info('Use --tool to run a tool, --profile to run a profile of tools')
        info('Multiple uses of --tool and/or --profile allowed')
        info('Use --list_tools and --list_profiles to see available options')
        # raise RuntimeError('x')
        # return os.OK  # USAGE NOINPUT NOTFOUND NOPERM
        return 1  # XXX generate exception

    # XXX If only doing offline analysis, don't need to be root.
    # Defer root check until after determined what tools are selected,
    # if each can be run as non-root, then proceed, else this error path.
    # Will need a boolean in the TOOLS and/or PROFILE struct, or at least
    # the resulting generated tool list, showing if tool is Live or Offline,
    # and if tool requires Root or not. Most live tools require root, a few do not.
    if not is_user_root():
        error('Root privileges needed to run. Retry with sudo.')
        # raise RuntimeError('x')
        # return os.OK  # USAGE NOINPUT NOTFOUND NOPERM
        return 1  # XXX generate exception

    if is_sudo_root():
        # debug('Configuring for SUDO usage')
        app_state['sudo_based_usage'] = True

    status = None
    pd = None
    prd = None
    # Build the list of tools to run, then run them.
    # debug('Generating list of selected tools..')
    (status, tool_count, _) = build_meta_profile()
    if status is False:
        error('Unable to build tool selection, exiting')
        tool_status = 1
    if tool_count > 0:
        # Defer creating any dirs until determine there are tools to run.
        status, pd, prd = create_directories()
        if status is False:
            error('Unable to create directories, exiting')
            return 1
        # At this point, PD and PRD should be ready to use.

        # start_results()  # XXX

        start_cpu = time.clock()
        start_real = time.time()
        # Run the tools!
        run_meta_profile(pd, prd)
        end_cpu = time.clock()
        end_real = time.time()
        # XXX save this in per-run stats. Also create per-tool time stats elsewhere.
        cpu_seconds = end_cpu - start_cpu
        real_seconds = end_real - start_real
        debug('Total CPU seconds: ' + str(cpu_seconds))
        debug('Total Seconds: ' + str(real_seconds))

        # Post-processing, after running the tools
        if is_sudo_root():
            # XXX need to fix PD dir perms, on first creation?
            debug('Changing SUDO root ownership/permissions to generated files..')
            if not change_generated_file_perms(prd):
                tool_status = 1
                error('Error occurred during chmod/chgrop post-processing')

        # create_shellscript()  # XXX
        # XXX create index file, with header, records, and footer of metadata.
        # html_file = os.path.join(prd, app_state['index_html_file'])
        # create_index_html(app_state['timestamp'], html_file)

        # enable zipped results, if user specified.
        # XXX Delete dir after creating zip.
        # if app_state['zip_results']:  # XXX
        #    debug('Creating ZIP file of results..')  # XXX
        #    zip_results()  # XXX

    # Cleanup and terminate.
    shutdown_message(tool_status)
    return tool_status

############################################################


# args.py


def parse_args():
    '''Parse the command line arguments.'''
    global app_state
    global TOOLS
    prolog = 'FirmWare Audit (FWAudit) is a platform firmware diagnostic tool.'
    epilog = 'For more information, please read the User Guide (README).'
    c = app_state['switchar']  # '/' or '-', depending on OS
    p = argparse.ArgumentParser(description=prolog, epilog=epilog,
                                prefix_chars=c, add_help=True)
    p.add_argument(c+'v', '--verbose',
                   action='store_true', default=False,
                   help='Use verbose output.')
    p.add_argument(c+'d', '--debug',
                   action='store_true', default=False,
                   help='Use debug output.')
#    p.add_argument('--logfile',
#                   action='store_true', default=False,
#                   help='Save results to logfile.')
    p.add_argument('--syslog',
                   action='store_true', default=False,
                   help='Send hashes over UNIX SysLog.')
    p.add_argument('--eventlog',
                   action='store_true', default=False,
                   help='Send hashes over Windows EventLog.')
    p.add_argument(c+'V', '--version',
                   action='store_true', default=False,
                   help='Show program version, then exit.')
    p.add_argument('--diags',
                   action='store_true', default=False,
                   help='Show diagnostic information, then exit.')
    p.add_argument('--list_tools',
                   action='store_true', default=False,
                   help='Show available tools, then exit.')
    p.add_argument('--list_profiles',
                   action='store_true', default=False,
                   help='Show available tool profiles, then exit.')
    p.add_argument(c+'t', '--tool',
                   action='append', default=None,
                   help='Specify <toolname> to run.')
    p.add_argument(c+'p', '--profile',
                   action='append', default=None,
                   help='Specify <profilename> to run.')
#    p.add_argument('--new_profile',
#                   action='append', default=None,
#                   help='Specify <JSONstring> of new custom profile.')
#    p.add_argument('--no_profile',
#                   action='store_true', default=False,
#                   help='Do not use builtin list of profiles.')
#    p.add_argument('--zip_results',
#                   action='store_true', default=False,
#                   help='Create ZIP file of resulting directory of output.')
    p.add_argument('--output_dir',
                   action='store', default=None,
                   help='Specify target directory to store generated files. Not compatible with sudo case, use as root or with su.')
    p.add_argument('--output_mode',
                   choices=('merged', 'out_first', 'err_first'),
                   action='store', default=app_state['output_mode'],
                   help='Specify how to log tool output. Currently for root use only, do not use with sudo use.')
 #   p.add_argument('--omit_pii',
 #                  action='store_true', default=False,
 #                  help='Omit known PII-centric data from results.')
    p.add_argument(c+'c', '--colorize',
                   action='store_true', default=False,
                   help='Use colored output for interactive console.')
    p.add_argument('--manifest',
                   action='store_true', default=False,
                   help='Generate manifest file of hashes for generated files.')
    p.add_argument('--nomanifest',
                   action='store_true', default=False,
                   help='Do not generate manifest files.')
    p.add_argument('--hash',
                   action='store_true', default=False,
                   help='Generate SHA256 sidecar hash files for generated files.')
    p.add_argument('--nohash',
                   action='store_true', default=False,
                   help='Do not generate sidecar hash files.')
    # tool-specific options:
#    # XXX no acpidump or acpixtract option!
#    p.add_argument('--chipsec_uefi_blacklist', action='store',
#                   default=get_tool_arg('chipsec_uefi_blacklist', 'rom_bin_file'),
#                   help='Rom.bin for UEFI blacklist.')
#    p.add_argument('--dmidecode_bin_file', action='store',
#                   default=get_tool_arg('dmidecode_decode', 'dmidecode_bin_file'),
#                   help='Binary file for dmidecode.')
#    p.add_argument('--chipsec_iommu_engine', action='store',
#                   default=None,  # machine-specific, no default
#                   help='Set <IommuEngineType>, listed in chipsec_util_iommu_list.')
#    p.add_argument('--chipsec_fw_type', action='store',
#                   default=None,  # machine-specific, no default
#                   help='Set <FirmWareType>, listed in chipsec_util_decode_types.')

    # argsparse returns options and args, we're only using args, fix.
    args = p.parse_args()

    if args.verbose:
        app_state['verbose'] = True
    if args.debug:
        app_state['debug'] = True
    if args.colorize:
        app_state['colorize'] = True
    if args.eventlog:
        app_state['eventlog_mode'] = True
    if args.syslog:
        app_state['syslog_mode'] = True
    if args.hash:
        app_state['hash_mode'] = True
    if args.nohash:
        app_state['hash_mode'] = False
    if args.manifest:
        app_state['manifest_mode'] = True
    if args.nomanifest:
        app_state['manifest_mode'] = False
    if args.version:
        app_state['version_mode'] = True
    if args.diags:
        app_state['diagnostic_mode'] = True
    if args.list_tools:
        app_state['list_tools_mode'] = True
    if args.list_profiles:
        app_state['list_profiles_mode'] = True
    # XXX all below option require user input validation
#    if args.no_profile:
#        app_state['no_profile'] = args.no_profile
#    if args.new_profile:
#        info('New user-defined profile(s)..')
#        app_state['new_profiles'] = args.new_profile
#        output_wrapped(app_state['new_profiles'])
    if args.profile:
        app_state['user_profiles'] = args.profile
    if args.tool:
        app_state['user_tools'] = args.tool
    if args.output_mode:
        app_state['output_mode'] = args.output_mode
    if args.output_dir:
        app_state['output_dir'] = args.output_dir
        app_state['output_dir_specified'] = True
        info('User has specified explicit parent directory of: ' + app_state['output_dir'])
#    if args.omit_pii:
#        app_state['omit_pii'] = True
    app_state['omit_pii'] = False

    # TOOLS-related options:

    # XXX replace set_tool_arg(x, y) with: TOOLS['x']['args'] = args.y
    # XXX user input validation for all tool strings
    # XXX MISSING acpidump/acpixtract file args!

#    # XXX user input validation for all tool strings
#    if args.chipsec_uefi_blacklist:
#        set_tool_arg('chipsec_uefi_blacklist', 'rom_bin_file', args.chipsec_uefi_blacklist)
#    if args.dmidecode_bin_file:
#        set_tool_arg('dmidecode_decode', 'dmidecode_bin_file', args.dmidecode_bin_file)
#    if args.chipsec_iommu_engine:
#        set_tool_arg('chipsec', 'chipsec_iommu_engine', args.chipsec_iommu_engine)
#        # TOOLS['chipsec_iommu_engine']['args'] = args.chipsec_iommu_engine
#    if args.chipsec_fw_type:
#        set_tool_arg('chipsec', 'chipsec_fw_type', args.chipsec_fw_type)
#        # TOOLS['chipsec_fw_type']['args'] = args.chipsec_fw_type

############################################################

# app_init.py


def show_tool_version():
    '''Show program version info, for use with --version option.'''
    log(APP_METADATA['short_name'] + ' v' +
        APP_METADATA['version'])


def startup_message():
    '''Show initial status information to user and logs.

    Send initial message to syslog, if --syslog specified.
    Send initial message to eventlog, if --eventlog specified.
    Send initial message to logfile, if --logfile specified.
    '''
    print()
    log(APP_METADATA['full_name'] + ' Version ' + APP_METADATA['version'])
    log('Copyright (C) ' + APP_METADATA['copyright'] + ' ' +
        APP_METADATA['full_author'] + '. All rights reserved.')
    if app_state['syslog_mode']:
        syslog_send(APP_METADATA['short_name'] + ': starting...')
    if app_state['eventlog_mode']:
        eventlog_send(APP_METADATA['short_name'] + ': starting...')
    print()


def shutdown_message(status):
    '''Show final status information to user and logs.

    Send final message to syslog, if --syslog specified.
    Send final message to eventlog, if --eventlog specified.
    Send final message to logfile, if --logfile specified.
    '''
    app_name = APP_METADATA['short_name']
    logmsg = None
    if status == 0:
        if app_state['verbose']:
            log('Program completed successfully')
        logmsg = app_name + ': exiting successfully'
    else:
        if app_state['verbose']:
            log('Program completed with error(s), status: ' + str(status))
        logmsg = app_name + ': exiting with error(s), status: ' + str(status)
    if app_state['syslog_mode']:
        syslog_send(logmsg)
    if app_state['eventlog_mode']:
        eventlog_send(logmsg)
    print()

############################################################

# logging.py
# Centralized print() and logging functions.
# Messages should resemble a complete sentence,
# starting with capital letter,
# and omit final punctuctuation (except for log() function).
# Using log log() is nearly the same as print().
# The log() code adds no prefix or suffix, presuming you will do it.
# The critical code wraps message between "ERROR: " and "!", and displays more info on the exception e.
# The error code wraps message between "ERROR: " and "!".
# The warning code wraps message between "WARNING: " and "!".
# The verbose code wraps message between "INFO: " and ".".
# The debug code wraps message between "DEBUG: " and ".".
# Use warning() to display WARNING (recoverable) messages.
# Use critical() to display ERROR (fatal exceptions) messages.
# Use error() to display ERROR (fatal) messages.
# Use info() to only display if --verbose specified.
# Use debug() to only display if --debug specified.
# Most output is for users and normal use.
# Debug output is for developers, for diagnosing defects.
# For max spew, use both --debug and --verbose.
# For min spew, use neither --debug or --verbose.


def output(msg):
    '''Final wrapper to print()'''
    try:
        print(msg)
    except UnicodeDecodeError:
        sys.exc_info()
        print(repr(msg)[1:-1])


def log(msg, suffix=None, prefix=None,
        prefix_fg_color=COLOR_DEFAULTS['log_pre_fg'],
        prefix_bg_color=COLOR_DEFAULTS['log_pre_bg'],
        msg_fg_color=COLOR_DEFAULTS['log_msg_fg'],
        msg_bg_color=COLOR_DEFAULTS['log_msg_bg']):
    '''Main logging function.

    Replaces Python print() function as main function to display output.
    Adds logfile and syslog and eventlog and colorized output.
    Output to console is either colorized or not, depending on user preference.

    In addition to console, output is also mirrored to a logfile and/or
    the OS logging service (UNIX syslog or Windows eventlog), depending
    on user preference.

    In addition to console output and syslog/eventlog output, logging will also
    mirror to an app-centric text file. NOTE: Logfile support is not ready yet.

    If colorized output is specified, interactive output is colorized.
    Output to syslog, eventlog, and logfiles are not colorized.
    Colorized output is accomplished using ANSI escape sequences. This
    works on most UNIX systems. On Windows, it requires a terminal
    that supports ANSI escape sequences.

    Most of the application uses log() to display output. This function
    does not recursively call itself, if it has to display an error, it uses
    print() -- uncolorized.

    msg -- the main text to log
    prefix -- String to prepend to text, eg '[DEBUG] ', or None if no prefix.
    suffix -- String to append to text, eg '!', or None if no suffix.
    prefix_fg_color -- One of FG_colors, or None if no color.
                       If None, the prefix will not be colored.
    prefix_bg_color -- One of COLORS BG_* colors, or None if no color.
    msg_fg_color -- One of COLORS FG_* colors or None if no color.
    msg_bg_color -- One of COLORS BG_* colors, or None if no color.
    max_buf_len -- Max length of buffer to attempt to log. Default is
                   app_state['max_buf'].

    Returns nothing (except the log output).
    '''
    # pass as syslog_level=x as optional arg.
    if msg is None:
        output('[ERROR] cannot output message if no message specifed!')
        return

    # XXX untested code:
    max_buf = app_state['max_buf']
    if len(msg) > max_buf:
        output('[ERROR] msg too long to log!, msg length=' + str(len(msg)) + ', max=' + str(max_buf) + '!')
        return

    if prefix is None:
        prefix = ''
    if suffix is None:
        suffix = ''
    if is_none_or_null(msg):
        msg = ''
        suffix = ''

    if app_state['colorize']:
        prefix_reset = COLORS['RESET']
        msg_reset = COLORS['RESET']
        if is_none_or_null(prefix):
            prefix_fg_color = ''
            prefix_bg_color = ''
            prefix_reset = ''
        if (is_none_or_null(prefix_fg_color)) or ((is_none_or_null(prefix_bg_color))):
            prefix_fg_color = ''
            prefix_bg_color = ''
            prefix_reset = ''
        if (is_none_or_null(msg_fg_color)) or ((is_none_or_null(msg_bg_color))):
            msg_fg_color = ''
            msg_bg_color = ''
            msg_reset = ''
        result = ''
        result += prefix_fg_color
        result += prefix_bg_color
        result += prefix
        result += prefix_reset
        result += msg_fg_color
        result += msg_bg_color
        result += msg
        result += suffix
        result += msg_reset
    else:
        result = prefix + msg + suffix
    output(result)

    # add logfile code here!

    # Send message to OS logging facility, uncolorized:
    # XXX pass integer status code, not just strings.
    if app_state['syslog_mode']:
        syslog_send(prefix + msg + suffix)
    if app_state['eventlog_mode']:
        eventlog_send(prefix + msg + suffix)


def warning(msg):
    '''Simple warning wrapper to log()'''
    if app_state['colorize']:
        log(msg, prefix='[WARNING] ', suffix='!',
            prefix_fg_color=COLOR_DEFAULTS['warn_pre_fg'],
            prefix_bg_color=COLOR_DEFAULTS['warn_pre_bg'],
            msg_fg_color=COLOR_DEFAULTS['warn_msg_fg'],
            msg_bg_color=COLOR_DEFAULTS['warn_msf_bg'])
    else:
        output(msg)


def critical(e, msg):
    '''Simple critical wrapper to log()'''
    # e.message  # Python 2-only
    # e.__cause__ # Python 3-only
    # e.__context__  # Python 3-only
    # e.__traceback__ # Python 3-only
    # # IOError errno (d), strerror (s), filename (?)
    if e is not None:
        log('Exception ' + str(e.errno) + ': ' + str(e.message),
            prefix_fg_color=COLOR_DEFAULTS['error_pre_fg'],
            prefix_bg_color=COLOR_DEFAULTS['error_pre_bg'],
            msg_fg_color=COLOR_DEFAULTS['error_msg_fg'],
            msg_bg_color=COLOR_DEFAULTS['error_msg_bg'])
    if app_state['colorize']:
        log(msg, prefix='[ERROR] ', suffix='!',
            prefix_fg_color=COLOR_DEFAULTS['error_pre_fg'],
            prefix_bg_color=COLOR_DEFAULTS['error_pre_bg'],
            msg_fg_color=COLOR_DEFAULTS['error_msg_fg'],
            msg_bg_color=COLOR_DEFAULTS['error_msg_bg'])
    else:
        output(msg)


def error(msg):
    '''Simple error wrapper to log()'''
    if app_state['colorize']:
        log(msg, prefix='[ERROR] ', suffix='!',
            prefix_fg_color=COLOR_DEFAULTS['error_pre_fg'],
            prefix_bg_color=COLOR_DEFAULTS['error_pre_bg'],
            msg_fg_color=COLOR_DEFAULTS['error_msg_fg'],
            msg_bg_color=COLOR_DEFAULTS['error_msg_bg'])
    else:
        output(msg)


def info(msg):
    '''Simple verbose wrapper to log()'''
    if app_state['verbose']:
        if app_state['colorize']:
            log(msg, prefix='[INFO] ', suffix='.',
                prefix_fg_color=COLOR_DEFAULTS['info_pre_fg'],
                prefix_bg_color=COLOR_DEFAULTS['info_pre_bg'],
                msg_fg_color=COLOR_DEFAULTS['info_msg_fg'],
                msg_bg_color=COLOR_DEFAULTS['info_msg_bg'])
        else:
            output(msg)


def debug(msg):
    '''Simple debug wrapper to log()'''
    if app_state['debug']:
        if app_state['colorize']:
            log(msg, suffix='.',
                prefix=None, prefix_fg_color=None, prefix_bg_color=None,
                msg_fg_color=COLOR_DEFAULTS['debug_msg_fg'],
                msg_bg_color=COLOR_DEFAULTS['debug_msg_bg'])
        else:
            output(msg)


def output_wrapped(msg, textwrap_length=72, nocolor=None):
    '''Wraps a list of strings to textwrap_length.'''
    sorted_msg = ', '.join(sorted(msg))
    wrapped_msg = textwrap.fill(sorted_msg, width=textwrap_length)
    if (nocolor is not None and nocolor) or (app_state['colorize']):
        log(wrapped_msg, suffix=None, prefix=None)
    else:
        output(wrapped_msg)


def eventlog_send(msg):
    debug('FIXME: implement eventlog handler')
    '''Mirrors log message output to eventlog, on Windows systems.
    
    Returns True if it worked, False if fails.
    '''
    # XXX Test string buffer limits before sending to eventlog
    if not EVENTLOG_AVAILABLE:
        output('[ERROR] Windows eventlog Python module not available!')
        return False
    if not os_is_windows():
        output('[ERROR] eventlog only available for Windows systems!')
        return False
    if not app_state['eventlog_mode']:
        output('[ERROR] eventlog code called but eventlog_mode False!')
        return False
    if is_none_or_null(msg):
        output('[ERROR] Empty message, nothing to send to eventlog!')
        return False
    try:
        # XXX eventlog.eventlog(msg)
        return True
    except:
        output('[ERROR] Logger failed to send message to Windows EventLog!')
        sys.exc_info()
        output('[WARNING] Disabling Windows EventLog mode after first error.')
        app_state['eventlog_mode'] = False
        return False
    return True


def syslog_send(msg):
    '''Mirrors log message output to syslog, on Unix-like systems.
    
    Returns True if it worked, False if fails.
    '''
    # XXX Test string buffer limits before sending to syslog
    if not os_is_unix():
        output('[ERROR] syslog only available for UNIX-based systems!')
        return False
    if not SYSLOG_AVAILABLE:
        output('[ERROR] syslog Python module not available!')
        return False
    if not app_state['syslog_mode']:
        output('[ERROR] syslog code called but syslog_mode False!')
        return False
    if is_none_or_null(msg):
        output('[ERROR] Empty message, nothing to send to syslog!')
        return False
    try:
        # syslog.syslog(syslog.LOG_INFO, msg)
        final_msg = APP_METADATA['short_name'] + ': ' + msg
        # print('[DEBUG] syslog message: ' + final_msg)
        syslog.syslog(final_msg)
        return True
    except:
        output('[ERROR] Logger failed to send message to Unix SysLog!')
        sys.exc_info()
        output('[WARNING] Disabling SysLog mode after first error.')
        app_state['syslog_mode'] = False
        return False
    return True


# XXX rename function
def log_stdio_func(buf_to_log, log_file_name):
    '''TBW'''
    try:
        _ = warn_if_overwriting_file('', log_file_name)
        log_file = open(log_file_name, 'w')
        log_file.write(buf_to_log)
        log_file.close()
    except:
        sys.exc_info()
    # XXX return pass/fail status upstream


############################################################

# hash.py


def return_hash_str_of_file(path):
    '''For a given file, return the sha256 hash string.
    
    Returns a SHA256 hash string if successful, None if unsuccessful.'''
    if is_none_or_null(path):
        error('Filename to hash unspecified')
        return None
    if not path_exists(path):
        error('File to hash does not exist: ' + path)
        return None
    debug('file to hash: ' + path)
    hash_str = None
    try:
        with open(path, 'rb') as f:
            buf = f.read()
            h = hashlib.sha256(buf)
            h.update(buf)
            hash_str = h.hexdigest()
            debug('hash: ' + hash_str)
    except OSError as e:
        critical(e, 'failed to hash file')
        hash_str = None
        sys.exc_info()
    return hash_str


def create_sidecar_hash_file(path):
    '''For a given file, create a 'side-car' hash file.
    
    Use a sha256sum-compatible file format, a single line consisting of:
        <hash> + <space> + <filename>
    XXX what newline format required?
    Future: Should support other formats, certutil.exe, etc. What formats?

    Returns True if successful, False if unsuccessful.'''
    if is_none_or_null(path):
        error('Filename to hash unspecified')
        return False
    if not path_exists(path):
        error('File to hash does not exist: ' + path)
        return False
    debug('path of file to hash: ' + path)
    base_filename = os.path.basename(path)
    if is_none_or_null(base_filename):
        error('Filename to hash unspecified')
        return False
    debug('base name of file to hash: ' + base_filename)
    hash_str = return_hash_str_of_file(path)
    if is_none_or_null(hash_str):
        error('Hash is empty')
        return False
    debug('hash of file: ' + hash_str)
    sidecar_path = path + '.sha256'
    if path_exists(sidecar_path):
        error('Sidecar hash file already exists, not overwriting')
        return False
    debug('sidecar filename: ' + sidecar_path)
    hash_results = hash_str + ' ' + base_filename
    debug('sidecar contents: ' + hash_results)
    try:
        with open(sidecar_path, 'wt') as f:
            f.write(hash_results)
    except OSError as e:
        critical(e, 'Problems creating sidecar hash file')
        sys.exc_info()
        return False
    debug('Finished creating sidecar file: ' + sidecar_path)
    return True


def create_sidecar_hash_files(path):
    '''For a given directory 'path', create a 'side-car' hash file for each file.

    Intended to be used in each Per-Tool-Directory (PTD), where tools
    are run, some and generate multiple files (eg, rom.bin, ACPI tables, ...)
    This code creates a 'side-car' hash file for each generated file
    (eg, rom.bin.sha256 for rom.bin, output.txt.sha256 for output.txt, ...).

    Run this before generating that directory's manifest.txt file.
    After running this, don't create any new files or modify any
    existing files in this directory. ...except for modifying file
    owner/group/attributes in the Unix sudo case.

    Returns True if successful, False if unsuccessful.'''
    # XXX Support (or fail with errors): dirs, files with links.
    # XXX can a hash have a space in it, which would require escaping?
    # XXX Support file with spaces or otherwise needing escaping
    # XXX How does sha256sum handle escaping files (eg, with spaces)?
    # XXX What other file formats are needed (eg, XML for one MSFT tool)?
    if is_none_or_null(path):
        error('Directory name to hash unspecified')
        return False
    if not dir_exists(path):
        error('Directory to hash does not exist: ' + path)
        return False
    debug('dir to hash: ' + path)
    hash_fn = None
    try:
        for root, dirs, files in os.walk(path):
            debug('root dir = ' + root)
            for fn in files:
                fqfn = path + os.sep + fn
                debug('file loop: filename = ' + fn)
                debug('file loop: fully-qualified filename = ' + fqfn)
                create_sidecar_hash_file(fqfn)
    except OSError as e:
        critical(e, 'Failed to create hash file')
        sys.exc_info()
        return False
    # XXX propogate status code upstream
    return True


############################################################

# tools-profiles.py


def show_tools_and_profiles():
    '''TBW.'''
    if app_state['user_tools'] is None:
        error('user_tools is None')
    if app_state['user_profiles'] is None:
        error('user_profiles is None')
    if app_state['new_profiles'] is None:
        error('new_profiles is None')
    app_state['tools_and_profiles'] = None
    if not app_state['no_profile']:
        app_state['tools_and_profiles'] += app_state['user_profiles']
    app_state['tools_and_profiles'] += app_state['new_profiles']
    app_state['tools_and_profiles'] = app_state['user_tools']


def list_profile_list(profiles, profile_name):
    '''List one profile list, the built-in or user-defined one(s).'''
    # XXX cleanup output, add column alignment
    if profile_name is None:
        error('Profile name is unspecified')
        return False
    if profiles is None:
        error('Profile list is unspecified')
        return False
    if not isinstance(profiles, list):
        error('All user-defined profiles must be in a list of 2 or more')
        error('A single profile entry will fail, code only handles a list')
        # XXX Write code that can detect a single profile struct, not list of 2+
        # is_valid_tool_dict(p)
        return False
    log('Displaying list of ' + profile_name + ' profiles')
    log('Profiles count: ' + str(len(profiles)))
    for p in profiles:
        # is_valid_tool_dict(p)
        log(p['name'] + ':  ' + p['desc'])
        # log(p['desc'], prefix=p['name'] + '  ', suffix='')
        for i, t in enumerate(p['tools']):
            log('    ' + str(i+1) + ':  ' + t)
            # log(t, prefix='    ' + str(i+1) + '  ', suffix='')
    return True


def list_profiles():
    '''List built-in and user-defined profiles.'''
    # XXX cleanup output, add column alignment
    if app_state['no_profile']:
        log('Disabling internal profile list.')
    else:
        list_profile_list(PROFILES, 'built-in')
    new_profiles = app_state['new_profiles']
    if (new_profiles is not None) and (new_profiles is not ''):
        # XXX untested codepath
        list_profile_list(new_profiles, 'user-defined')


def list_tools():
    '''User specified --list_tools, list available tools.'''
    log('Available tool count: ' + str(len(TOOLS)))
    # XXX cleanup output, add column alignment
    for i, tool in enumerate(TOOLS):
        msg = tool['name'] + ':  ' + tool['desc']
        log(msg, prefix=str(i) + '  ', suffix='')


def get_tool_arg(toolns, key):
    '''Return argument of a tool, given a toolns.

    TOOLS['chipsec_iommu_engine']['args'] = args.chipsec_iommu_engine
    TOOLS['chipsec_util_spi_dump']['args'] = args.chipsec_rom_bin_file
    value = get_tool_arg(toolns, key)
    Remove this once I can figure out how to use Python dictionaries properly.
    '''
    # arg_value = TOOLS[tool_ns]['args'][arg_key]
    # debug('toolns=' + tool_ns + ', arg_key=' + arg_key + 'arg_value=' + arg_value)
    # XXX need to add key after args!!
    if is_none_or_null(toolns):
        error('Tool namespace not specified')
        return None
    if not is_valid_tool(toolns):
        error('Invalid tool namespace: ' + toolns)
        return None
#    for t in TOOLS:
#        tool_name = t['tool']
#        ns = t['name']
#        tool_args = t['args']
#        if not isinstance(expected_rc, int):
#            error('Expected RC is not an Integer')
#            return (None, None)
#        if toolns == ns:
#            debug('SUCCESS, valid tool ' + tool_name + ', args= ' + str(tool_args))
#            return tool_args
#    error('Invalid toolns: ' + toolns)
    # Traverse TOOLS list, finding toolns entry.
    for i, t in enumerate(TOOLS):
        #tool_name = t['tool']
        tool_ns = t['name']
        tool_args = t['args']
        #tool_expected_rc = t['exrc']
        if tool_ns == toolns:
            # debug('Valid tool ' + tool_ns)
            try:
                value = tool_args[key]
                debug('Toolns=' + toolns + ', key=' + key + ', value=' + value)
                return value
            except KeyError:
                debug('KeyError exception, key not valid: ' + key)
                return None
            debug('Tool not found!')
    return None


def set_tool_arg(toolns, key, value):
    '''Set the value of a tool arg.

    UGLY HACK until I can get this to work:
    TOOLS['chipsec_util_spi_dump']['args'] = args.chipsec_rom_bin_file
    aka:
    set_tool_arg('chipsec_util_spi_dump', 'chipsec_rom_bin_file')
    '''
    if value is None:
        error('No arg value specified, cannot set arg value')
        return False
    if key is None:
        error('No arg key specified, cannot lookup arg value')
        return False
    if toolns is None:
        error('No tool name specified, cannot lookup arg value')
        return False
    for i, t in enumerate(TOOLS):
        tool_ns = t['name']
        tool_args = t['args']
        if tool_ns != toolns:
            debug('Valid tool ' + tool_ns)
            try:
                value = tool_args[key]
                debug('Toolns=' + toolns + ', key=' + key + ', value=' + value)
                return value
            except KeyError:
                debug('KeyError exception, key not valid: ' + key)
                return None
    error('Invalid tool ' + toolns)
    return None


def is_valid_tool(lookup_name):
    '''
    Is specified lookup_name a valid tool name?

    Traverse 'TOOLS', comparing lookup_name to tools[i].name.

    lookup_name -- Tool name to validate.

    Returns True if valid, False if not.
    '''
    for i, t in enumerate(TOOLS):
        tool_ns = t['name']
        # debug('is_valid_tool(): tool_name = ' + tool_ns)
        if tool_ns == lookup_name:
            # debug('Valid tool ' + lookup_name)
            return True
    error('Invalid tool ' + lookup_name)
    return False


def is_valid_profile(lookup_profile,
                     use_builtin_list=True,
                     use_user_list=False):
    '''Is specified lookup_profile a valid profile name?

    Traverse 'profiles', comparing lookup_profile to profiles[i].name.
    Depending on use_builtin_list and/or use_user_list, checks the
    PROFILE list or the user-defined app_state['valid_profile'] list.

    lookup_profile -- name of profile to lookup.
    use_builtin_list -- if True, validate against PROFILE list.
    use_user_list -- if True, validate against user-defined list.

    Returns True if valid, False if not.
    '''
    if lookup_profile is None:
        error('Lookup failed, lookup name not specified')
        return False
    if use_builtin_list and PROFILES is None:
        error('Lookup failed, empty built-in profile list')
        return False
    if use_user_list and app_state['valid_profiles'] is None:
        error('Lookup failed, empty profile list')
        return False
    if use_builtin_list:
        for p in PROFILES:
            if p['name'] == lookup_profile:  # p.name
                # debug('SUCCESS, valid profile: ' + p.name)
                return True
        warning('No valid profile in built-in profile list')
    if use_user_list:
        for p in app_state['valid_profiles']:
            if p.name == lookup_profile:
                # debug('SUCCESS, valid profile: ' + p.name)
                return True
        warning('No valid profile in user-defined profile list')
    return False

#####################################################################


# run.py
#
# High-level view of exec functions:
# main()/parse_args() -- get profile from user (or single tool name),
#                        and create top-level dir if specified.
#   run_profile() -- loop through all tools in profile (or single tool name),
#                     and create per-tool dir, then run tool.
#     select_tool() -- select proper tool namespace name from TOOLS list.
#       tool_resolver() -- many if statements to run the specified tool.
#         spawn_process() -- run a native process, in specified dir.
#           or
#         call_chipsec_main(), run chipsec_main-based module, in specified dir.
#           or
#         call_chipsec_util(), run chipsec_util-based module, in specified dir.
#
# XXX Refactor spawn_process and call_chipsec_(util,main):
# saves stdout/stderr to a file
# creates sidecar hash files for all generated files
#
# XXX how to deal with dependencies of live data by offline tools,
# Presuming below case 1 is mainstream use and case 3 is seldom use.
# Types of usage of online/offline test combos:
# 1) during same run, user specifies both live and offline tools.
# Needs to do live first, then offline.
# Only create profiles that don't cause this conflict.
# 2) with reliance on previously-generated live data?
# require full paths to all input, otherwise fail.
# 3) during same run, do live analysis of current system,
# and also offline analysis of previously-generated live data.
# This differs from case 1, case 1 uses currently-generated live input as
# output for current offline input.
# This case uses previously-generate live input as output for current
# offline input. Will this be a problem?
# Solve by:
# Not letting user mix live/offline tests and also specify old data,
# require mixing live/offline is case 1.
# Create 2 separate profile names, run fwaudit twice.
#
# XXX Make code run under Python 3 or 2.
# Chipsec-specific exec code must be in v2, need to
# isolate chipsec exec code# to a Python2-centric module.
# Main code can then run using either v2 or v3,
# When using incompatible versions, exec external python2.
# When running under python3, exec external python2.
#
# XXX Have --external_python_exec bool option, if specified,
# use external exec to run Python, instead of same-process modules.
#
# XXX Integrate chipsec main/util execs, native exec, same args and code.
#
# XXX Create a single run_test(), run_profile(), proper args.
# spawn_process(verbose, cmd, start_dir, expected_rc, log_file_prefix)
# update python/native exec code to return similar stuff.
# update python/native exec code to pass similar args.
# for call_chipsec_util/call_chipsec_main, add args:
#    show_stdio=True, log_stdio=True, hash_stdio=True):
# refactor io-logging code in exec_native and share with python_exec code.


def spawn_process(args, start_dir, expected_rc, toolns,
                  show_stdio=True, log_stdio=True, hash_stdio=True,
                  verbose=False):
    ''' Execute a native process (not a Python module).

    Spawns a single native process.
    Not responsible for creating any directory.
    Upstream must provide create before calling.

    cmd -- name of command to run. Process name and arguments are in list.
           Fails if cmd is empty, nothing to run. FIXME.
           LIST of strings, first is command, rest are args
    verbose -- If True, emit verose output.
    start_dir -- Starting directory for child process. If empty, run in cwd!
                 Fails if specified start_dir directory does not exist.
    expected_rc -- Expected return code of child process.
    toolns -- Serves two purposes:
                      The name of single tool in TOOLS list to run.
                      The file prefix for stdio log files,
                      if log_stdio is True.
                      Fails if toolns is empty, FIXME.
    show_stdio -- If True, display output of child process to stdout.
    log_stdio -- If True, log output of child processes saved to file(s).
    hash_stdio -- If True, generate sidecar hash files for all generated
                  files. Must also have log_stdio set to true, need to
                  generate files before creating any create sidecar hashes.

    Returns returncode of child process.
    '''
    # XXX Create logfiles based on log_file_prefix.
    # XXX Test on macOS, FreeBSD for single shared UNIX codepath.
    # XXX Create related functions for Windows and UEFI.
    # XXX deal with subdirs!
    # before profile loop:
    # test if top_level_dir exists
    # if top_level_dir does not exist, error or warn? Exit?
    # mkdir top-level dir
    # should we cd into top-level dir?
    # If so, have to save cwd at beginning, restore at end.
    # XXX our status codes overlap with tool expected value, resolve
    if args is None:
        error('Empty arguments, nothing to exec')
        return -1
    if is_none_or_null(args[0]):
        error('Program name empty, nothing to exec')
        return -2
    if is_none_or_null(toolns):
        error('Tool namespace empty')
        return -3
    if is_none_or_null(start_dir):
        error('Per-tool target directory is empty')
        return -4
    if not dir_exists(start_dir):
        error('Per-tool target directory does not exist: ' + start_dir)
        return -5
    # XXX is this next if statement still useful?
    if hash_stdio and not log_stdio:
        error('Cannot hash stdio if it is not logged')
        return -6
    # info('Process starting directory: ' + start_dir)

#    # convert string list to a single space-delimited string
#    for arg in args:
#        debug('arg=' + arg)
#    debug('expected_rc=' + str(expected_rc))
    # debug('program=' + cmd + ', dir=' + start_dir + ', ns=' + toolns + ', erc=' + expected_rc)
    # Spawn the process, get the resulting stdout/stderr and return code.
    # stdout_buf = ''
    # stderr_buf = ''
    # debug('stdout_buf len = ' + str(len(stdout_buf)))
    # debug('stderr_buf len = ' + str(len(stderr_buf)))

#    debug('BYPASSING any mode selection, hardcoded to merged output')
    mode = app_state['output_mode']
    if is_none_or_null(mode):
        error('Unspecified output mode')
        return -5
    # debug('mode: ' + mode)
    if mode == 'merged':
        # debug('Initialize handles for merged output')
        child_stdin = subprocess.PIPE
        child_stdout = subprocess.PIPE
        child_stderr = subprocess.PIPE
    elif mode == 'out_first':
        # debug('Initialize handles for out_first output')
        child_stdin = subprocess.PIPE
        child_stdout = subprocess.PIPE
        child_stderr = subprocess.STDOUT
    elif mode == 'err_first':
        # debug('Initialize handles for err_first output')
        child_stdin = subprocess.PIPE
        child_stdout = subprocess.PIPE
        child_stderr = subprocess.STDOUT
    else:
        error('Unknown output mode: ' + mode)
        return -6

    debug('pre-exec: tool="' + args[0] + '", ns="' + toolns + '", cwd="' + start_dir + '"')
    try:
        # XXX use Popen(bufsiz=x, executable=x,
        if is_none_or_null(start_dir):
            error('Start_dir is empty or none')
            return -7
        debug('Start_dir: ' + start_dir)
        process = subprocess.Popen(args,
                                   stdin=child_stdin,
                                   stdout=child_stdout,
                                   stderr=child_stderr,
                                   cwd=start_dir)
        # shell=False)
        # universal_newlines=True)
        stdout_buf, stderr_buf = process.communicate(input=None)
        # stdout_buf = bytes.decode(stdout_buf)
        # stderr_buf = bytes.decode(stderr_buf)
        # XXX what is max buf size of Python lib? What if tests generate more?

        if is_none_or_null(stdout_buf):
            # debug('There is no STDOUT to display')
            stderr_buf = ''

        if is_none_or_null(stderr_buf):
            # debug('There is no STDERR to display')
            stderr_buf = ''

        if process.returncode != expected_rc:
            status_string = 'FAIL'
            warning(status_string + ': ' +
                    'post-exec: ' +
                    'rc=' + str(process.returncode) +
                    ', erc=' + str(expected_rc) +
                    ', out=' + str(len(stdout_buf)) +
                    ', err=' + str(len(stderr_buf)))
        else:
            status_string = 'PASS'
            debug(status_string + ': ' +
                 'post-exec: ' +
                 'rc=' + str(process.returncode) +
                 ', erc=' + str(expected_rc) +
                 ', out=' + str(len(stdout_buf)) +
                 ', err=' + str(len(stderr_buf)))

    # XXX check for access denied and file not found.
    except subprocess.CalledProcessError as e:
        critical(e, 'Unexpected exception invoking process')
        sys.exc_info()

    # Log stdout/stderr, based on user preference.
    # debug('Post-exec, about to show child stdio..')
    if not show_tool_stdio(start_dir, toolns, stdout_buf, stderr_buf,
                           show_stdio, log_stdio, hash_stdio):
        error('Unable to save post-exec child process output')
    # XXX need to move this upstream where they have hash?
    if app_state['eventlog_mode']:
        # XXX add hashes to results
        debug('Logging exec results to eventlog')
        log_exec_results(args, toolns, process.returncode, status_string)
    if app_state['syslog_mode']:
        # XXX add hashes to results
        debug('Logging exec results to syslog')
        log_exec_results(args, toolns, process.returncode, status_string)
    debug('Exiting exec code, rc=' + str(process.returncode))
    return process.returncode


def init_stdio_streams():
    '''Initialize child process stdio handles, based on user input.

    Sets child proess stdout/stderr streams. Merging means redirecting
    STDERR to STDOUT for a single stream. 'No_*' means redirecting either
    STDOUT or STDERR to DEVNULL, advanced users only!

    Returns a tuple of (stdin, stdout, stderr).
    '''
    # The default mode: merged stdout and stderr buffers (all PIPE)
    child_stdin = subprocess.PIPE
    child_stdout = subprocess.PIPE
    child_stderr = subprocess.PIPE
    mode = app_state['output_mode']
    # XXX Fix below guessed redir strings with actual ones.
    # XXX Need shellscript output filenames here, using tool-less prefix names.
    if mode == 'merged':
        debug('Merging tool output, sending STDERR to STDOUT')
        app_state['shell_script_redir_string'] = '1>2>output.txt'
    elif mode == 'out_first':
        debug('Splitting tool output, STDOUT then STDERR')
        child_stderr = subprocess.STDOUT
        app_state['shell_script_redir_string'] = '1>stdout.txt 2>stderr.txt'
    elif mode == 'err_first':
        debug('Splitting tool output, STDERR then STDOUT')
        child_stderr = subprocess.STDOUT
        app_state['shell_script_redir_string'] = '1>stdout.txt 2>stderr.txt'
    else:
        error('Unexpected mode: ' + mode)
        return (None, None, None)
    debug('shell redir string: ' + app_state['shell_script_redir_string'])
    return (child_stdin, child_stdout, child_stderr)


def show_tool_stdio(start_dir, toolns, stdout_buf, stderr_buf, show_stdio, log_stdio, hash_stdio):
    '''Display and/or log tool stdout/stderr, based on user config.

    After child process has been executed, depending on user config options,
    display child stdout and/or stderr, and/or and/or log to a file.

    toolns -- prefix name of tool that generated output.
    stdout_buf -- buffer of stdout.
    stderr_buf -- buffer of stderr.
    show_stdio -- should child tool output be displayed to parent output?
    log_stdio -- should output be logged to a file?
    hash_stdio -- generate sidecar hash files for all output file(s)?

    The app_state['output_mode'] that control if stdout or stderr is shown
    first or second only applies to console output. For syslog and
    eventlog output, stderr is shown before stdout.

    Return True if things work as expected, False is something fails.
    '''
    # XXX how to test for max buf sizes, passed as args in Python?
    # XXX conflict: arg -vs- show_stdio = app_state['show_stdio']?
    mode = app_state['output_mode']
    if is_none_or_null(mode):
        error('Mode not specified')
        return False
    if is_none_or_null(toolns):
        error('No child tool name specified')
        return False
    if ((stdout_buf is None) and (stderr_buf is None)):
        warning('Child process STDOUT and STDERR buffers empty')
    if stdout_buf is None:
        warning('Child process STDOUT buffer empty')
    if stderr_buf is None:
        warning('Child process STDERR buffer empty')

    try:
        # Initialize output filename(s)
        stdout_filename = toolns + '.stdout.txt'
        stderr_filename = toolns + '.stderr.txt'
        if mode == 'merged':
            stdout_filename = toolns + '.output.txt'
            stderr_filename = None

        if stdout_filename is None:
            debug('No stdout file')
            stdout_file = None
            return False
        else:
            stdout_file = os.path.join(start_dir, stdout_filename)
            debug('stdout filename: ' + stdout_file)

        if stderr_filename is None:
            if mode != 'merged':
                stderr_file = None
                error('No stderr file, output mode NOT merged')
                return False
        else:
            stderr_file = os.path.join(start_dir, stderr_filename)
            debug('stderr filename: ' + stderr_file)

        debug('starting dir: ' + start_dir)

        if show_stdio:
            # debug('Showing stdio..')
            if (is_none_or_null(stdout_buf)) and (is_none_or_null(stderr_buf)):
                warning('Both stdout and stderr buffers are none or empty')
                # XXX return error or continue?)

            if mode == 'merged':
                if not is_none_or_null(stdout_buf):
                    debug('Showing merged STDOUT+STDERR..')
                    output(stdout_buf)
            elif mode == 'err_first':
                if not is_none_or_null(stderr_buf):
                    debug('Showing STDERR..')
                    output(stderr_buf)
                if not is_none_or_null(stdout_buf):
                    debug('Showing STDOUT..')
                    output(stdout_buf)
            elif mode == 'out_first':
                if not is_none_or_null(stdout_buf):
                    debug('Showing STDOUT..')
                    output(stdout_buf)
                else:
                    debug('No STDOUT to show')
                if not is_none_or_null(stderr_buf):
                    debug('Showing STDERR..')
                    output(stderr_buf)
                else:
                    debug('No STDERR to show')
            else:
                debug('Internal error, unexpected mode: ' + mode)
                return False

        if log_stdio:
            # debug('Logging stdout to syslog..')
            if not is_none_or_null(stdout_buf):
                log_stdio_func(stdout_buf, stdout_file)
            if mode != 'merged':
                if not is_none_or_null(stderr_buf):
                    log_stdio_func(stderr_file, stderr_buf, stderr_file)

    except OSError as e:
        critical(e, 'Unexpected exception occurred')
        sys.exc_info()
    return True

#####################################################################

# unsorted.py


def log_exec_results(args, toolns, rc, status_string):
    '''Log post-exec status, tool name + rc + hash to OS log'''
    # XXX , sha256_hash):
    # XXX add this to the python exec code, not just native exec.
    # XXX What is max limit of a Windows EventLog message?
    # XXX What is max limit of a Mac/Linux/FreeBSD SysLog message?
    our_name = APP_METADATA['short_name']
    if is_none_or_null(status_string):
        error('No status string specifed')
        return False
    if is_none_or_null(toolns):
        error('No test name specifed, cannot exec null')
        return False
    if args is None:
        error('No argument specified')
        return False
    if rc is None:
        error('No return code specified')
        return False
    log_msg = our_name + ': status=' + status_string + ': test=' + toolns + ', rc=' + str(rc)
#        'sha256=' + sha256_hash
    debug('syslog/eventlog message: ' + log_msg)
    if app_state['eventlog_mode']:
        debug('Logging exec results to Windows EventLog..')
        eventlog_send(log_msg)
    if app_state['syslog_mode']:
        debug('Logging exec results to UNIX SysLog..')
        syslog_send(log_msg)
    return True


def log_results(module_rc, module_name):
    '''
    Log PASS/FAIL results for a single test.

    Simple function that saves pass/fail status code for a given test.
    '''
    # XXX modify this to export data to the database, and/or one more logfile.
    # current output is to stdio, it needs to go to a SQL/etc database, or
    # each record recorded to an XML/other file.
    if module_rc > 0:
        log('PASS: module ' + str(module_name) + ': ' + str(module_rc))
    else:
        log('FAIL: module ' + str(module_name) + ': ' + str(module_rc))


def traverse_dir(dirname):
    '''Traverse a directory, counting dirs/files and bytes used.

    dirname -- The root directory to begin traversal.

    Returns a tuple of (status, dirs, files bytes) where:

    status -- True if function worked, False if there was a problem.
              If False, other falses in the returned tuple are None.
    dirs -- count of dirs
    files -- count of files
    bytes -- count of all files used (bytes)

    FIXME: THIS CODE DOES NOT HANDLE onerror!!
    '''
    # XXX add callback function for onerror, track errors!!!!!
    # XXX handle errors
    # By default, errors from the listdir() call are ignored.
    # If onerror is specified, it should be a function;
    # it will be called with one argument, an OSError instance.
    # It can report the error to continue with the walk,
    # or raise the exception to abort the walk.
    # That the filename is available as the filename attribute
    # of the exception object.
    # XXX handle links
    # By default, walk() will not walk down into symlinks that resolve to dirs.
    # Set followlinks to True to visit dirs pointed to by symlinks, on systems
    # that support them. Setting followlinks to True will fail if a link points
    # to a parent dir of itself. walk() does not keep track of the dirs it
    # visited already.
    dirs = files = total_bytes = 0
    if is_none_or_null(dirname):
        error('Directory name not specified')
        return (False, dirs, files, total_bytes)
        # return (False, None, None, None)
    if not dir_exists(dirname):
        error('Directory name does not exist')
        return (False, dirs, files, total_bytes)
        # return (False, None, None, None)
    total_bytes = 0
    try:
        for root, dirs, files in os.walk(dirname,
                                         topdown=True,
                                         onerror=None,
                                         followlinks=False):
            if root != dirname:
                error('Returned directory name different: ' + root)
                # return (False, None, None, None)
                return (False, dirs, files, total_bytes)
            # debug('File count: ' + str(len(files)))
            # debug('Dir count: ' + str(len(dirs)))
            for name in files:
                total_bytes += os.path.getsize(os.path.join(root, name))
                debug('Total file size (bytes): ' + str(total_bytes))
    except OSError as e:
        critical(e, 'Unexpected exception occurred walking directory')
        sys.exc_info()
        # return (False, None, None, None)
        return (False, dirs, files, total_bytes)
    # debug('Successfully walked directory, returning actual data')
    return (True, dirs, files, total_bytes)

#######################################


def get_parent_directory_name():
    '''Get the name of the Parent Directory (PD).

    Sets app_state['output_dir'], if user has not already specified an directory
    via --output_dir. On Unix, when sudo used, dir is changed from root-based to
    pre-sudo user-based.

    Return True if successful, False if there was a problem.'''
    # XXX Does upstream code test if dir does not exist, and create or fail?
    if app_state['output_dir_specified']:
        debug('User specified output dir')
        _dir = app_state['output_dir']
        if is_none_or_null(_dir):
            error('User-specified parent directory is empty')
            return False
    else:
        _dir = get_default_directory_name()
        if is_none_or_null(_dir):
            error('Directory is null')
            return False
        # Note: returned path has trailing path separator (/, \)!
        app_state['output_dir'] = _dir + 'fwaudit.results'
    debug('Output parent directory: ' + app_state['output_dir'])
    return True


def get_default_directory_name():
    '''Get the name of the directory where the Parent Directory is.

    Get the OS-centric directory name where the 'Parent Directory' (PD) is located.
    Note: Downstream code presumes trailing path separator.

    Return string of dir, or None if failure.'''
    _dir = None
    if os_is_unix():
        if app_state['sudo_based_usage']:
            try:
                _sudo_user = os.getenv('SUDO_USER')
                if is_none_or_null(_sudo_user):
                    error('SUDO_USER environment variable is null')
                    return None
                if os_is_macos():
                    _dir = os.path.expanduser('~') + '/'
                else:
                    _dir = '/home/' + _sudo_user + '/'
                debug('Parent Dir (updated for SUDO usage) = ' + _dir)
            except:
                error('Unable to get SUDO user home directory')
                sys.exc_info()
                return None
        else:
            try:
                _dir = os.environ['HOME']
                _dir = _dir + '/'
                #debug('Parent Dir (NOT updated for SUDO usage) = ' + _dir)
            except:
                error('Unable to get HOME environment variable')
                sys.exc_info()
                _dir = None
            if is_none_or_null(_dir):
                error('HOME environment variable is empty')
                _dir = None
    elif os_is_windows():
        debug('Getting dir of Windows system')
        _dir = '%APPDATA%\\Roaming\\'  # XXX untested codepath!
    elif os_is_uefi():
        debug('Getting dir of UEFI Shell system')
        _dir = 'fs0:\\'  # XXX untested codepath!
    else:
        error('Unsupported target OS')
        _dir = None
    if is_none_or_null(_dir):
        error('Generated home directory is null')
    return _dir


def sudo_user_diags():
    '''For Unix SUDO use case, get pre-SUDO username.'''
    # What is FSB/POSIX standard for '/home/' + username?
    # win32api: GetUserName() and GetUserNameEx()
    # Is root always 0 (EUID==0?) on all modern *nix systems?
    # How to deal with Linux Capabilities?
    # How to deal with SELinux?
    # How to deal with Linux ACLs?
    # How to deal with BSD...?
    try:
        sudo_user = os.getenv('SUDO_USER')
        debug('getenv(SUDO_USER) username: ' + sudo_user)
        sudouser_home_dir = '/home/' + sudo_user
        debug('Homedir = ' + sudouser_home_dir)
    except:
        debug('Unable to view SUDO_USER')
    user = os.getenv('USER')
    logname_username = os.getenv('LOGNAME')
    # username = pwd.getpwuid(os.geteuid()).pw_name
    pwname_username = pwd.getpwuid(os.getuid()).pw_name
    username = getpass.getuser()
    userhome = os.path.expanduser('~')
    debug('getenv(LOGNAME) username: ' + logname_username)
    debug('pwd.getpwuid.pw_name: ' + pwname_username)
    debug('getpass.getuser() username: ' + username)
    debug('expanduser(~) home dir: ' + userhome)
    debug('getenv(USER) username: ' + user)
    logname_home_dir = os.path.expanduser('~' + logname_username + '/')
    debug('Homedir = ' + logname_home_dir)
    pwname_home_dir = os.path.expanduser('~' + pwname_username + '/')
    debug('Homedir = ' + pwname_home_dir)


def set_groups(path, new_uid, new_gid, verbose=True):
    '''For sudo case, set GID to non-SuperUser value.'''
    if not app_state['sudo_based_usage']:
        debug('set_groups: called for non-sudo use')
        return False
    try:
        debug('Changing file owner: file=' + path + ', uid=' + str(new_uid))
        new_gid_list = []
        new_gid_list = os.getgroups()
        if verbose:
            debug('os.getgroups: new_gid_list: ' + str(new_gid_list))
        os.setgroups([])
        if verbose:
            debug('calling os.setgroups(' + str(new_gid_list) + ')..')
        # os.setgroups(new_gid_list)  # XXX macOS: ValueError: too many groups
        os.setgroups([new_gid_list[0]])  # XXX macOS: ValueError: too many groups
        if verbose:
            debug('calling os.setgid(' + str(new_gid) + ')..')
        os.setgid(new_gid)
    except OSError as e:
        critical(e, 'Unable to to update UID on file: ' + path)
        sys.exc_info()
        log('Exception ' + str(e.errno) + ': ' + str(e))
        return False
    return True


def set_owner(path, new_uid, new_gid):
    '''For sudo case, set UID to non-SuperUser value.'''
    if not app_state['sudo_based_usage']:
        debug('set_owner: called for non-sudo use')
        return False
    try:
        debug('Changing file owner: file=' + path + ', uid=' + str(new_uid))
        os.chown(path, new_uid, new_gid)
    except OSError as e:
        critical(e, 'Unable to update GID on file: ' + path)
        sys.exc_info()
        return False
    return True


def change_file_owner_group(path, new_uid, new_gid):
    '''For Unix SUDO use case, modify existing root-owned file to pre-SUDO user.'''
    if not app_state['sudo_based_usage']:
        debug('set_owner: called for non-sudo use')
        return True
    if path is None:
        error('No path specified')
        return False
    if new_uid is None:
        error('No UID specified')
        return False
    if new_gid is None:
        error('No GID specified')
        return False
    debug('Changing file owner/group/mode: ' + path + ',' + str(new_uid) + ', ' + str(new_gid))
    owner_status = set_owner(path, new_uid, new_gid)
    group_status = set_groups(path, new_uid, new_gid)
    if (not owner_status) or (not group_status):
        debug('Unable to set file ownership/group')  # XXX error()
        return False
    return True


def change_file_mode(path, new_mode):
    '''For Unix SUDO use case, modify existing file attributes.'''
    # XXX how to determine which to set, user or sudo?
    if not app_state['sudo_based_usage']:
        debug('Not updating file mode, not using sudo')
        return True
    if path is None:
        error('No path specified')
        return False
    if new_mode is None:
        error('No file mode specified')
        return False
    try:
        os.chmod(path, new_mode)
    except OSError as e:
        critical(e, 'Unable to modify mode on path: ' + path)
        sys.exc_info()
        return False
    return True


def change_generated_file_perms(path, verbose=False):
    '''Change file ownership of a sudo-created file to it's non-root user.

    After the tools have been run, traverse the per-run-directory (PRD)
    and update all the files that the tools have generated, fixing the
    file ownerships from sudo'ed 'root' to the actual user, so the user
    can view the resulting files w/o having to become superuser.
    Eg: change_owner_and_attributes("rom.bin", "nobody", "nogroup", 436)

    Returns 0 if successful, 1 if an error occurred.'''
    if not app_state['sudo_based_usage']:
        debug('Not updating file owner/group/mode, not using sudo')
        return True
    if not os_is_unix():
        error('Only for UNIX-style OSes')
        return False
    cur_uid = os.getuid()
    if cur_uid != 0:
        error('UID nonzero: User is not SuperUser')
        return False
    debug('current UID: ' + str(cur_uid))
    cur_euid = os.geteuid()
    if cur_euid != 0:
        error('EUID nonzero: User is not SuperUser')
        return False
    debug('current EUID: ' + str(cur_euid))
    if path is None:
        error('Must specify path to set')
        return False
    # XXX This whole section: duplicate code, use existing function
    new_uid = int(os.environ.get('SUDO_UID'))
    if new_uid is None:
        error('Unable to obtain SUDO_UID')
        return False
    new_gid = int(os.environ.get('SUDO_GID'))
    if new_gid is None:
        error('Unable to obtain SUDO_GID')
        return False
    # XXX Read-only works for FILE, but need Write support for DIRs.
    # new_mode = ( stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH )
    # new_mode = stat.S_IREAD | stat.S_IRUSR | stat.S_IRGRP
    r_mode = (stat.S_IRUSR|stat.S_IRGRP|stat.S_IROTH)
    rw_mode = (stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IWGRP|stat.S_IROTH|stat.S_IWOTH)
    rwx_mode = (stat.S_IRWXU|stat.S_IRWXG|stat.S_IRWXO) 
    new_dir_mode = rwx_mode
    new_file_mode = rwx_mode
    debug('new file mode: ' + str(new_file_mode))
    debug('new dir mode: ' + str(new_dir_mode))
    for root, dirs, files in os.walk(path):  
        debug('root dir = ' + root)
        for d in dirs:  
            debug('dir = ' + d)
            joined = os.path.join(path, d)
            debug('joined dir = ' + joined)
            change_file_owner_group(joined, int(new_uid), int(new_gid))
            change_file_mode(joined, int(new_dir_mode))
        for f in files:
            debug('file = ' + f)
            joined = os.path.join(root, f)
            debug('joined file = ' + joined)
            change_file_owner_group(joined, int(new_uid), int(new_gid))
            change_file_mode(joined, int(new_dir_mode))
    # XXX propogate status code upstream
    return True


def build_meta_profile(verbose=True):
    '''Build meta profile, a list of all selected tools to run.

    Given the input app_state['user_tools'] and app_state['user_profiles'],
    create app_state['meta_profile'], the list of tools to run, a List of
    Strings, one string per toolns.

    Available profiles are in the built-in PROFILES list. User can extend
    profiles by using --new_profile to specify 1-N new profiles. User can
    bypass the built-in profile list by using --no_profile, in which case
    they must specify new profiles via --new_profile. Available tools are
    in the built-in TOOLS list, and are not user-extensible.

    If user's selection of tool(s)/profile(s) includes duplicate entries
    -- multiple copies of the same tool -- that will fail -- the PTD will
    have already been created for 2nd-subsequent uses. Need to check for
    duplicates. For now, document to not run multiple copies of the same
    tool.

    Returns a tuple of (status, count, skipped), where:
    status -- True if code worked, False if it failed.
    count -- count of selected tools in meta_profile
    skipped -- count of selected unrecognized tools skipped.
    '''
    # XXX check for duplicate tool entries, warn and skip dups
    # XXX can also check for dup tools when creating ptd, check if already exists.
    # XXX Remove verbose arg, or at least sync with global.
    app_state['meta_profile'] = []
    tools = 0
    skipped = 0
    if (app_state['user_profiles'] is None) and (app_state['user_tools'] is None):
        error('No profile(s) or tool(s) selected, nothing to do')
        return (False, tools, skipped)
    if (app_state['no_profile']) and (app_state['new_profiles'] is None):
        warning('Profiles are disabled')
        # XXX this codepath previously returned False. Does any below code presume the previous return?

    # Enumerate user selected tool(s) list.
    if app_state['user_tools'] is not None:
        if verbose:
            output_wrapped(app_state['user_tools'])
        for t in app_state['user_tools']:
            if is_valid_tool(t):
                debug('Adding tool to meta_profile: ' + t)
                app_state['meta_profile'].append(t)
                tools += 1
            else:
                warning('Ignoring unrecognized tool: ' + t)
                skipped += 1
                # return False   XXX?

    # Enumerate user-selected profile(s) list.
    if app_state['user_profiles'] is not None:
        output_wrapped(app_state['user_profiles'])
        if app_state['no_profile']:
            debug('Examining user-defined profiles')
            for p in app_state['user_profiles']:
                debug('User profile: ' + str(type(p['name'])))  # XXX
                debug('User profile: ' + p['name'])
                if p in enumerate(app_state['user_profiles']):  # XXX .keys()?
                    debug('Matches profile: ' + p['name'])
                    for t in enumerate(p['tools']):
                        if is_valid_tool(t):
                            debug('Adding tool to meta_profile: ' + t)
                            app_state['meta_profile'].append(t)
                            tools += 1
                        else:
                            skipped += 1
                            warning('Ignoring unrecognized tool: ' + str(t))
                            # return False   XXX?
        else:
            info('Examining built-in profiles')
            # for p in enumerate(app_state['user_profiles']):
            for p in app_state['user_profiles']:
                if verbose:
                    info('Profile: ' + str(type(p['name'])))
                info('Profile: ' + p['name'])
                if p in enumerate(PROFILES):  # XXX .keys()?
                    if verbose:
                        info('Matches profile: ' + p['name'])
                    for t in enumerate(p['tools']):
                        if is_valid_tool(t):
                            if verbose:
                                info('Adding tool to meta_profile: ' + t)
                            tools += 1
                            app_state['meta_profile'].append(t)
                        else:
                            skipped += 1
                            warning('Ignoring unrecognized tool: ' + str(t))
                            # return False   XXX?

    debug('Tool count: ' + str(tools))
    debug('Skipped count: ' + str(skipped))
    if skipped > 0:
        warning('Total skipped tool count: ' + str(skipped))
    return (True, tools, skipped)


def create_directories():
    '''Setup PD and PTD, including dealing with SUDO root -vs- user dir.

    Return True if successful, False if not.'''

    (new_dir_mode, new_uid, new_gid) = get_sudo_user_group_mode()

    # Part 1 of 3:
    # Setup Parent Directory (PD), before referencing PRD or PTD.
    # Get the name of PD
    _dir = get_parent_directory_name()
    if is_none_or_null(_dir):
        error('Parent directory name unspecified')
        return False, None, None
    # Create PD
    if setup_parent_directory(new_dir_mode, new_uid, new_gid) is False:
        error('Cannot create parent directory (PD), exiting')
        return False, None, None
    pd = app_state['output_dir']
    # debug('PD setup: ' + pd)

    # Part 2 of 3:
    # Setup Per-Run Directory (PRD), after PD is setup, before PTDs used.
    if not setup_per_run_directory(pd, new_dir_mode, new_uid, new_gid):
        error('Cannot create per-run directory (PRD), exiting')
        return False, None, None
    prd = app_state['per_run_directory']
    # debug('PRD setup: ' + prd)

    # Part 3 of 3: the Per-Tool-Directories (PTDs), happens elsewhere.

    return True, pd, prd


def setup_per_run_directory(pd, new_dir_mode, new_uid, new_gid):
    '''Create the per-run directory, if it doesn't already exist.

    Must be called after Parent Directory (PD) has been created.
    Must be called before any tools are run.

    Returns True if successful, False if not.
    '''
    # XXX UCT timezone usage
    stamp_format = '%Y%m%d%H%M%S' # '%Y%m%d_%H%M%S_%f'
    ts = time.gmtime()
    timestamp = time.strftime(stamp_format, ts)
    app_state['timestamp'] = timestamp
    prd = os.path.join(pd, timestamp)
    os.mkdir(prd)
    if is_none_or_null(prd):
        error('Per-run directory name unspecified')
        return False
    if not dir_exists(prd):
        error('Per-run directory does not exist: ' + prd)
        return False
    app_state['per_run_directory'] = prd
    debug('Per-run-directory: ' + prd)
    if app_state['sudo_based_usage']:
        debug('Changing owner/group of PRD...')
        change_file_owner_group(prd, new_uid, new_gid)
        debug('Changing attribs of PRD...')
        change_file_mode(prd, new_dir_mode)
    return True


def get_sudo_user_group_mode():
    '''TBW'''
    # XXX only need uid, gid, and file mode for sudo case...
    new_uid = int(os.environ.get('SUDO_UID'))
    if new_uid is None:
        error('Unable to obtain SUDO_UID')
        return False
    #debug('new UID via SUDO_UID: ' + str(new_uid))
    new_gid = int(os.environ.get('SUDO_GID'))
    if new_gid is None:
        error('Unable to obtain SUDO_GID')
        return False
    #debug('new GID via SUDO_GID: ' + str(new_gid))
    # new_dir_mode = (stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IWGRP|stat.S_IROTH|stat.S_IWOTH)
    rwx_mode = (stat.S_IRWXU|stat.S_IRWXG|stat.S_IRWXO)
    new_dir_mode = rwx_mode
    #debug('new dir mode: ' + str(new_dir_mode))
    return (new_dir_mode, new_uid, new_gid)


def setup_per_tool_directory(pd, prd, ptd, toolns):
    '''Create the per-tool directory.'''
    if is_none_or_null(ptd):
        error('Per-tool-directory name unspecified')
        return False
    if dir_exists(ptd):
        if not is_dir_empty(ptd):
            error('Skipping non-empty per-tool-directory: ' + ptd)
            return False
        warning('Using existing empty per-tool directory: ' + ptd)
    else:
        try:
            os.mkdir(ptd)
            if not dir_exists(ptd):
                error('Problems creating per-tool-directory')
                return False
        except OSError as e:
            critical(e, 'Problems creating per-tool-directory')
            sys.exc_info()
            return False
    (new_dir_mode, new_uid, new_gid) = get_sudo_user_group_mode()
    change_file_owner_group(ptd, new_uid, new_gid)
    change_file_mode(ptd, new_dir_mode)
    if not dir_exists(ptd):
        error('Target per-tool directory was not created: ' + ptd)
        return False
    return True


def setup_parent_directory(new_dir_mode, new_uid, new_gid):
    '''Create the parent directory, if it doesn't already exist.

    Must be called before any use of the Per-Run Directory (PRD)
    or the Per-Tool Directory (PTD) of each toolns.

    If Unix user has used SUDO to become SuperUser, then the 
    PD must be changed from default root-based to original user-based,
    so after SUDO command, the resulting files are in the user's 
    subdir, not in the root dir.

    If user specifies their own PD, then should not modify location.

    What to do if user foo has an existing PD, and ALSO the root
    has an existing PD? Two users separately using fwaudit, two
    separate datasets. Warn? Merge? How to fail properly?

    Returns True if successful, False if not.
    '''
    pd = app_state['output_dir']
    if is_none_or_null(pd):
        error('Parent directory name unspecified')
        return False
    # By now, PD string should exist. Create dir, if it doesn't already exist.
    if dir_exists(pd):
        debug('Parent directory already exists: ' + pd)
        return True
    debug('Parent directory does not exist, creating: ' + pd)
    try:
        os.mkdir(pd)
        if not dir_exists(pd):
            error('Parent directory was not created')
            return False
    except OSError as e:
        critical(e, 'Failed to create parent directory: ' + pd)
        sys.exc_info()
        return False
    # XXX only do this if using sudo codepath
    debug('Updating owner/attribs of Parent Directory')
    change_file_owner_group(pd, new_uid, new_gid)
    change_file_mode(pd, new_dir_mode)
    return True


def run_meta_profile(pd, prd):
    '''Loop through and run each of the tools in the meta_profile.'''
    # XXX check pd, prd for Null or None and if dir_exists
    if is_none_or_null(pd):
        error('Input PD is none or null')
        # return False
    if is_none_or_null(prd):
        error('Input PRD is none or null')
        # return False
    pd = app_state['output_dir']
    prd = app_state['per_run_directory']
    if is_none_or_null(pd):
        error('Unable to obtain PD')
        return False
    if is_none_or_null(prd):
        error('Unable to obtain PRD')
        return False
    # For each tool to run, create it's target per-tool-directory.
    for toolns in app_state['meta_profile']:
        try:
            ptd = os.path.join(prd, toolns)
            if not setup_per_tool_directory(pd, prd, ptd, toolns):
                error('Unable to create per-tool-directory')
                return False
            else:
                debug('Created per-tool directory: ' + ptd)
            # At this point, we should have a PRD/PTD dir setup to run tool in.
        except OSError as e:
            critical(e, 'OSError trying to create tool directory')
            sys.exc_info()
            # XXX: check if OSError is File Not Found
            # except FileNotFoundError as e:
            # error('File Not Found: tool needs to be installed in PATH')
            return False
        # Call tool resolver, to determine which variation (namespace) of a tool to run
        rc = tool_resolver(toolns, pd, prd, ptd)
        # XXX Confirm failure rc is logged in tool_resolver() or finish_results()
        debug('Post-tool-resolution, rc = ' + str(rc))
        if app_state['hash_mode']:
            if not create_sidecar_hash_files(ptd):
                error('Unable to create side-car hash file(s) in PTD directory: ' + ptd)
                return False
        if app_state['manifest_mode']:
            debug('***** MANIFEST MODE:.....')
            if not create_manifest_file(ptd):
                error('Unable to create PTD manifest file in directory: ' + ptd)
                return False
    # finish_results()
    # XXX propogate error upstream
    return True


def get_pass_fail_status(toolns, tool, rc, erc):
    debug('Expected_rc=' + str(erc) + ', rc=' + str(rc))
    erc = rc  # XXX mock success, fix properly!
    if rc == erc:
        status = 'PASS'
    else:
        status = 'FAIL'
    debug('tool=' + tool + ', ns=' + toolns + ', rc=' + str(rc) + ', erc=' + str(erc) + ', status=' + status)
    return status


def tool_resolver(toolns, pr, prd, ptd):
    '''Run user-specified tool.

    Traverse test_list, looking for a match; if found, run that one tool.

    There are multiple ways to call a given tool, a toolns is unique per
    tool-usage, one toolns per tool func. 'Resolver' is a fancy way of
    saying this function correlates the toolns with the proper function
    name.

    name -- toolns to run.
    start_dir -- per-tool-directory to start process as cwd
    expected_rc -- expected status code to check against actual

    Return status code of tool to upstream caller.
    '''
    # XXX This is horrible code, refactor away completely.
    # XXX Post 0.0.2, replace this ugly code with:
    # better TOOLS dict,
    # template native exec function,
    # template python module exec function,
    # external stub to deal with chipsec module invocation.
    # delete all the single tool functions, and this multi-if function.
    # Refactor, one resolver per tool.
    # Refactor futher, one template function for all tools,
    # store all per-tool data in TOOLS struct, so user can
    # add new tools as well as new profiles.
    # Store per-tool TOOLS structs in toolname.py,
    # along with the tools functions.
    # Upstream code merges all available tools' TOOLS structs
    # into a single, etc.
    # XXX rc conflicts with tool errorcode!
    # XXX (i, p, f) = post_tool_exec(i, p, f, rc, tool_name, mode_online, ns)
    # XXX normalize name exec_* etc in tool worker functions.
    # XXX expected RC for chipsec code!
    # XXX integrate below 3 lists, ('built-in', native exec, and Python module
    # load), then alphabetize
    # XXX resolve acpidump live output not working as acpixtract offline input.
    rc = 1
    if is_none_or_null(prd):
        error('No per-run directory specified')
        return rc
    if is_none_or_null(toolns):
        error('No tool namespace specified')
        return rc
    if not is_valid_tool(toolns):
        error('Invalid tool name specified')
        return rc
    if not dir_exists(prd):
        error('Per-run directory does not exist: ' + prd)
        return rc

    rc = 0
    # At this point, we have the toolns as 'key' to unique tool to run.
    # We need other basics about this tool, tool name (eg, chipsec),
    # and the expected return code, to pass to downstream code that
    # will resolve/exec the code. Upstream code from this point has
    # only been referring to tool by toolns name.
    # XXX replace get_tool_info() with proper dict/list use to access TOOL.
    # tool = None
    # erc = None
    tool, erc = get_tool_info(toolns)
    if is_none_or_null(tool):
        error('Tool name is None or not specified')
        return rc
    if is_none_or_nonint(erc):
        error('Expected rc is None or non-Integer')
        return rc

    if tool == 'acpidump':
        rc = acpidump(toolns, tool, prd, ptd, erc)
    elif tool == 'acpixtract':
        rc = acpixtract(toolns, tool, prd, ptd, erc)
    elif ((tool == 'chipsec') or (tool == 'chipsec_util') or (tool == 'chipsec_main')):
        rc = chipsec(toolns, tool, prd, ptd, erc)
    elif tool == 'dmidecode':
        rc = dmidecode(toolns, tool, prd, ptd, erc)
    elif tool == 'flashrom':
        rc = flashrom(toolns, tool, prd, ptd, erc)
    elif tool == 'fwts':
        rc = fwts(toolns, tool, prd, ptd, erc)
    elif tool == 'INTEL-SA-00075-Discovery-Tool':
        rc = intel_amt_discovery(toolns, tool, prd, ptd, erc)
    elif tool == 'intel_sa00086.py':
        rc = intel_me_detection(toolns, tool, prd, ptd, erc)
    elif tool == 'lsusb':
        rc = lsusb(toolns, tool, prd, ptd, erc)
    elif tool == 'lspci':
        rc = lspci(toolns, tool, prd, ptd, erc)
    elif tool == 'lshw':
        rc = lshw(toolns, tool, prd, ptd, erc)
    elif tool == 'pawn':
        rc = pawn(toolns, tool, prd, ptd, erc)
    else:
        error('Unknown tool name, unable to resolve: ' + toolns)
        return -1  # XXX ?
    debug(tool + ' post-exec: rc=' + str(rc) + ', expected=' + str(erc))
    status = get_pass_fail_status(toolns, tool, rc, erc)

    # add_results_record(tool, ptd, toolns, rc, erc, status)
    # XXX more to add to results record:
    # hashes of generated files
    # spawn code needs to add some results to results_record,
    # like generated stdio files.

    # walk ptd to discover unexpectedly-generated files

    return rc


def get_tool_info(toolns):
    '''Return info about a tool, given a toolns.

    Returns the name and expected_rc given an expected_rc.
    Needed since meta_profile has list of toolns strings, but
    tool resolver also needs tool name and expected_rc for a given toolns.

    Remove this once I can figure out how to use Python dictionaries properly.
    '''
    # arg_value = TOOLS[tool_ns]['args'][arg_key]
    # debug('toolns=' + tool_ns + ', arg_key=' + arg_key + 'arg_value=' + arg_value)
    if is_none_or_null(toolns):
        error('Tool namespace not specified')
        return (None, None)
    if not is_valid_tool(toolns):
        error('Invalid tool namespace: ' + toolns)
        return (None, None)
    # Traverse TOOLS list, finding toolns entry.
    tool_name = None
    expected_rc = None
    for i, t in enumerate(TOOLS):
        tool_name = t['tool']
        tool_ns = t['name']
        expected_rc = t['exrc']
        if not isinstance(expected_rc, int):
            error('Expected RC is not an Integer')
            return (None, None)
        if toolns == tool_ns:
            # debug('SUCCESS, valid tool ' + tool_name)
            return (tool_name, expected_rc)
    error('Unrecognized tool namespace: ' + toolns)
    return (None, None)


#####################################################################

# util.py


def fail_if_missing(tool, fname):
    '''Failure wrapper to path_exists().

    Returns 0 if file exists, 1 if file does not exist.
    '''
    if not path_exists(fname):
        error('"' + tool + '": missing file "' + fname + '"')
        return 1
    return 0


def warn_if_overwriting_file(tool, fname):
    '''Warning wrapper to path_exists().

    Returns True if file exists, False if not.
    '''
    if path_exists(fname):
        warning('"' + tool + '": overwriting file "' + fname + '"')
        return True
    return False


def dir_exists(path, verbose=False):
    '''Check if a directory exists, returns True if exists, False if not.'''
    if is_none_or_null(path):
        warning('dir_exists(): Directory name not specified')
        return False
    try:
        if os.path.isdir(path) and os.access(path, os.F_OK) and os.access(path, os.R_OK):
            if verbose:
                debug('Directory exists and is readable: ' + path)
            return True
        if verbose:
            debug('Directory missing or unreadable: ' + path)
        return False
    except:
        error('Unexpected exception checking for dir: ' + path)
        sys.exc_info()
        return False


def path_exists(path):
    '''Check if a file exists, returns True if exists, False if not.'''
    if is_none_or_null(path):
        error('Cannot check if path exists if the input is null')
        return False
    try:
        if os.path.isfile(path) and os.access(path, os.F_OK) and os.access(path, os.R_OK):
            # info('File exists and is readable: ' + path)
            return True
        # debug('path_exists(): File missing or unreadable: ' + path)
        return False
    except:
        error('Unexpected exception verifying path: ' + path)
        sys.exc_info()
        return False

def is_tty(stream):
    '''Returns True if stream is a TTY, False if not.'''
    if not hasattr(stream, 'isatty'):
        return False
    if not stream.isatty():
        return False  # auto color only on TTYs
    return True


def is_root():
    '''Returns True if user is running as root, False if not.'''
    uid = os.getuid()
    if uid == 0:
        debug('User is ROOT, UID: ' + str(uid))
        return True
    else:
        debug('User is NOT root, UID: ' + str(uid))
        return False


def switch_character():
    '''Return the OS-specific command line option switch character.'''
    if os.altsep is not None:
        return os.altsep
    if os_is_uefi():
        return '/'
    elif os_is_windows():
        return '/'
    else:  # UNIX:
        return '-'


def is_none_or_nonint(i):
    '''Returns True if int is None or non-int, else returns False.'''
    return bool(((i is None) or (not isinstance(i, int))))


def is_none_or_nonbool(b):
    '''Returns True if bool is None or non-bool, else returns False.'''
    return bool(((b is None) or (not isinstance(b, bool))))


def is_none_or_null(s):
    '''Returns True if str is None or non-str, else returns False.'''
    # Rename to is_none_or_null_string()
    # return bool(((s is None) or (isinstance(s, str)) or (s is '')))
    return bool(((s is None) or (s is '')))


def os_is_uefi():
    '''Returns True if OS is UEFI Shell, False if not.'''
    # XXX what is proper test for UEFI target? CPython2 and MicroPython
    if platform.system() is 'UEFI':   # XXX untested code
        return True
    debug('platform.system: ' + platform.system())
    return False


def os_is_windows():
    '''Returns True if OS is Windows, False if not.'''
    if 'Windows' in platform.system():
        return True
    return False


def os_is_linux():
    '''Returns True if OS is Linux, False if not.'''
    if 'Linux' in platform.system():
        return True
    return False


def os_is_freebsd():
    '''Returns True if OS is FreeBSD, False if not.'''
    if 'FreeBSD' in platform.system():
        return True
    return False


def os_is_macos():
    '''Returns True if OS is macOS, False if not.'''
    if 'Darwin' in platform.system():
        return True
    return False


def os_is_unix():
    '''Returns True if OS is Unix-based, False if not.'''
    if os_is_linux() or os_is_freebsd() or os_is_macos():
        return True
    return False


def is_sudo_root():
    '''Returns True if user is root via sudo, False if not.'''
    if not is_unix_user_root():
        error('User is not SuperUser')
        return False
    uid = os.getenv('SUDO_UID')
    if uid == None:
        error('No SUDO_UID set')
        return False
    # info('User is SUDO root')
    return True


def is_windows_user_administrator():
    '''Check if Windows user has Administrator privs

    Returns True if admin, False if not.
    This will not work on CygWin.
    Calls the Win32 API IsUserAnAdmin() to make check.
    Older versions of Windows (eg, WinXP) don't support this API.
    Required modules: os, ctypes

    :return: True if Administrator, False if not.
    '''
    # XXX Which Windows versions support this API?
    if not os_is_windows():
        error('Windows-centric code should not be called from this OS')
        return -1  # XXX generate exception
    try:
        if ctypes.windll.shell32.IsUserAnAdmin() == 1:
            return True
    except:
        error('Unexpected exception occurred')
        sys.exc_info()
        pass
    return False


def is_unix_user_root():
    '''Check if UNIX user is Root or otherwise has Super User privs.

    :return: True if root, False if not.
    '''
    if not os_is_unix():
        error('Unix-centric code should not be called from this OS')
        return -1  # XXX generate exception
    try:
        euid = os.geteuid()
        uid = os.getuid()
        if ((euid == 0) and (uid == 0)):
            return True
    except:
        error('Unexpected exception occurred')
        sys.exc_info()
        pass
    return False


def is_user_root():
    '''Check if user is root.

    Try both Windows-centric Administrator and Unix-centric root checks.

    :return: True if root, False if not.
    '''
    win_admin = False
    unix_root = False
    if os_is_windows():
        win_admin = is_windows_user_administrator()
        if not win_admin:
            warning('User is not Windows Administrator')  # XXX disable colorizing
    if os_is_unix():
        unix_root = is_unix_user_root()
        # show_sudo_vars()
        if not unix_root:
            warning('User is not Unix root')  # XXX disable colorizing
    root = (win_admin or unix_root)
    return root


def diagnose_groups(uid_name_string, gid_name_string):
    '''TBW'''
    # XXX test when user and/or root is a member of multiple groups
    # test if macOS/FreeBSD behavior is the same as Linux. See the Python
    # documentation Note for os.getgroups() and os.setgrups().
    for (name, passwd, gid, members) in grp.getgrall():
        debug('name=' + name + ',  gid=' + str(gid) + ', members=' + str(members))
        # if username in members: gids.append(gid)
    all_groups = grp.getgrall()
    # output_wrapped(all_groups)
    # debug(str(all_groups))
    #for g in all_groups:
        #output_wrapped(str(g))
        # debug(str(g))
    groups = os.getgroups()
    #for g in groups:
        #output_wrapped(str(g))
        # debug(str(g))
    gname = gid_name_string
    uname = uid_name_string
    print('uname: ' + uname)
    print('gname: ' + gname)

    if not os_is_macos():
        gid = int(grp.getgrnam(gname)[2])
        uid = int(grp.getgrnam(gname)[2])
        print('grname uid: ' + str(uid))
        print('grname gid: ' + str(gid))

        uid = int(pwd.getpwnam(uname).pw_uid)
        gid = int(grp.getgrnam(gname).gr_gid)
        print('pwname uid: ' + str(uid))
        print('grname gid: ' + str(gid))

    cur_uid = os.getuid()
    cur_uid_name = pwd.getpwuid(os.getuid())[0]
    cur_gid = os.getgid()
    cur_group = grp.getgrgid(os.getgid())[0]
    print('uid: ' + str(cur_uid))
    print('uid name: ' + str(cur_uid_name))
    print('gid: ' + str(cur_gid))
    print('group: ' + str(cur_group))


def show_sudo_vars():
    '''Show SUDO-centric environment variables, on Unix.

    NOTE: Only supports SuperUser via SUDO.
    WARNING: No support for SU, or logging in as root!'''
    # XXX study best practices to determining sudo.
    # if not 'SUDO_UID' in os.environ.keys():
    if not os_is_unix():
        debug('Non-UNIX OS does not implement SUDO')
        return
    command = user = uid = None
    command = os.getenv('SUDO_COMMAND')
    user = os.getenv('SUDO_USER')
    uid = os.getenv('SUDO_UID')
    if not is_none_or_null(command):
        debug('SUDO_COMMAND = ' + command)
    if not is_none_or_null(user):
        debug('SUDO_USER = ' + user)
    if not is_none_or_null(uid):
        debug('SUDO_UID = ' + uid)


def show_user_group_process_info():
    '''TBW'''
    # XXX environment variable stuff is Unix-centric
    # XXX UID/GID/EGID is Unix-centric.
    try:
        pid = os.getpid()
        uid = os.getuid()
        gid = os.getgid()
        pgrp = os.getpgrp()
        ppid = os.getppid()
        # egid = os.getegid()
        # euid = os.geteuid()
        (ruid, euid, suid) = os.getresuid()
        (rgid, egid, sgid) = os.getresgid()
    except:
        error('Unable to get user/process/group info.')
        sys.exc_info()
        return
    if ((uid == 0) and (euid == 0)):  # XXX or?
        info('User is ROOT.')
    else:
        info('User is NOT root.')
    log('UID=' + str(uid) +
        ', GID=' + str(gid) +
        ', EUID=' + str(euid) +
        ', EGID=' + str(egid) +
        ', RUID=' + str(ruid) +
        ', RGID=' + str(rgid) +
        ', SUID=' + str(suid) +
        ', SGID=' + str(sgid) +
        ', PID=' + str(pid) +
        ', PPID=' + str(ppid) +
        ', PGRP=' + str(pgrp))
    # XXX which to use, os.environ['s'] or getenv('s')?
    try:
        user = os.environ['USER']
        home = os.environ['HOME']
        logname = os.environ['LOGNAME']
        log('HOME     = ' + home)
        log('USER     = ' + user)
        log('LOGNAME  = ' + logname)
    except:
        error('Unable to get env info.')
        sys.exc_info()
        return
    try:
        cwd = os.getcwd()
        log('cwd = ' + cwd)
        getuid_name = pwd.getpwuid(os.getuid())[0]
        log('uid0 name = ' + getuid_name)
        getlogin_name = os.getlogin()
        log('login name = ' + getlogin_name)
    except:
        error('Unable to get system info.')
        sys.exc_info()


def show_environment_variable(var_name):
    '''Show the name/value pair of a single environment variable. '''
    try:
        # XXX input validation
        if is_none_or_null(var_name):
            error('no environment variable name specified')
            return False
        var_value = os.getenv(var_name)
        if var_value is not None:
            log(var_name + '=' + var_value)
            return 1
        else:
            return 0
    except OSError as e:
        critical(e, 'showenv: OSError exception occurred')
        sys.exc_info()
    return False


def show_python_environment_variables():
    '''Show Python's environment variables.'''
    python_vars = [
        'PYTHONCASEOK',
        'PYTHONDEBUG',  # -d (if an int, then how many d's)
        'PYTHONDONTWRITEBYTECODE',  # -B
        'PYTHONHASHSEED',  # -R
        'PYTHONHOME',
        'PYTHONINSPECT',  # -i
        'PYTHONIOENCODING',
        'PYTHONNOUSERSITE',  # -s
        'PYTHONOPTIMIZE',  # -O (if an int, then how many O's)
        'PYTHONPATH',
        'PYTHONSTARTUP',
        'PYTHONUSERBASE',
        'PYTHONUNBUFFERED',  # -u
        'PYTHONVERBOSE',  # -v (if an int, then how many v's)
        'PYTHONWARNINGS',
        'PYTHONY2K',
        ]
    count = 0
    for v in python_vars:
        count += show_environment_variable(v)
    return count


def show_diagnostics():
    '''Show information to aid in bug reporting and debugging.'''
    # sys.implementation
    # sys.implementation.name
    # platform.python_implementation())
    # identify OEM name and system, in main, not just here.
    # 32-bit or 64-bit HW and OS
    # BIOS or UEFI-based, or other...
    # manufacturer of CPU. Eg, AMD can't run CHIPSEC tests.
    log('Diagnostic information:')
    debug('diagnosing root groups..')
    diagnose_groups("root", "root")
    #debug('diagnosing user groups..')
    #diagnose_groups("user", "user")
    print()
    sudo_user_diags()
    print()
    show_user_group_process_info()
    print()
    # Returns the (real) processor name, e.g. 'amdk6', or empty
    cpu = platform.processor()
    if (cpu is not None) or (cpu is not ''):
        log('Processor = ' + cpu)
    else:
        log('NOTE: this Python implementation does not support platform.processor().')
    log('platform.machine: ' + platform.machine())
    log('Hardware endianness: ' + sys.byteorder)
    log('Target platform: ' + sys.platform)
    log('platform.uname: ' + str(platform.uname()))
    log('platform.system: ' + platform.system())
    log('platform.platform.aliased: ' + platform.platform(aliased=True))
    log('platform.platform.terse: ' + platform.platform(terse=True))
    log('platform.release: ' + platform.release())
    log('platform.version: ' + platform.version())
    print()
    log('Python executable: ' + sys.executable)
    log('Python version: ' + sys.version)
    (py_major, py_minor, py_micro, py_release, py_serial) = sys.version_info
    log('Python version {}.{}.{}'.format(py_major, py_minor, py_micro))
    log('Python serial: ' + str(py_serial))
    log('Python release: ' + py_release)
    log('platform.node: ' + platform.node())
    log('Python compiler: ' + platform.python_compiler())
    log('Python API version: ' + str(sys.api_version))
    branch = platform.python_branch()
    if (branch is not None) or (branch is not ''):
        log('Python branch: ' + branch)
    else:
        log('NOTE: this Python implementation does not support platform.python_branch().')
    print()
    log('Max Integer: ' + str(sys.maxint))
    log('Max List: ' + str(sys.maxsize))
    log('Max Unicode: ' + str(sys.maxunicode))
    log('String encoding: ' + sys.getdefaultencoding())
    log('Filename encoding: ' + sys.getfilesystemencoding())
    log('sys.prefix: ' + sys.prefix)
    log('os.sep: ' + os.sep)
    log('os.extsep: ' + os.extsep)
    log('os.curdir: ' + os.curdir)
    log('user site: ' + str(site.ENABLE_USER_SITE))
    log('site USER_BASE: ' + site.USER_BASE)
    log('site USER_SITE: ' + site.USER_SITE)
    print()
    log('Python environment variable(s):')
    count = show_python_environment_variables()
    if count == 0:
        log('    <none>')
    print()
    log('Sys.path:')
    for p in sys.path:
        log(p)
    print()
    log('Sys.argv:')
    output_wrapped(sys.argv)
    print()
    log('Sys.builtin_module_names:')
    output_wrapped(sys.builtin_module_names)
    print()
    log('Sys.modules.keys:')
    output_wrapped(sys.modules.keys())
    print()
    log('Hash algorithms available:')
    output_wrapped(hashlib.algorithms_available)
    print()


def supported_os(verbose=False):
    '''Identify the host operating system.

    Check if OS is supported. adjust OS logging if not available.
    Return True if recognized, False if not.'''
    if verbose:
        info('platform.system: ' + platform.system())
        info('platform.release: ' + platform.release())
        info('sys.platform: ' + sys.platform)
        info('os.name: ' + os.name)
    recognized_os = True
    if os_is_unix():
        if app_state['syslog_mode'] and not SYSLOG_AVAILABLE:
            warning('UNIX SysLog module not available')
            info('Continuing with SysLog support disabled')
            app_state['syslog_mode'] = False
        if app_state['eventlog_mode']:
            warning('UNIX does not support Window EventLog logging')
            info('Continuing with EventLog support disabled')
            app_state['eventlog_mode'] = False
    elif os_is_uefi():
        debug('UEFI Shell codepath is untested..')
        if app_state['syslog_mode']:
            warning('UEFI does not support UNIX SysLog logging')
            info('Continuing with SysLog support disabled')
            app_state['syslog_mode'] = False
        if app_state['eventlog_mode']:
            warning('UEFI does not support Window EventLog logging')
            info('Continuing with EventLog support disabled')
            app_state['eventlog_mode'] = False
    elif os_is_windows():
        debug('Windows codepath is untested..')
        if app_state['eventlog_mode'] and not EVENTLOG_AVAILABLE:
            warning('Windows EventLog module not available')
            info('Continuing with EventLog support disabled')
            app_state['eventlog_mode'] = False
        if app_state['syslog_mode']:
            warning('Windows does not support UNIX SysLog logging')
            info('Continuing with SysLog support disabled')
            app_state['syslog_mode'] = False
    else:
        recognized_os = False
        error('Unsupported platform (patches appreciated)')
    return recognized_os


def supported_python(
        verbose=False,
        required_impl='CPython',
        required_major=2,
        required_minor=7):
    '''Check if using the proper type/version of Python.

    Check what implementation of Python we're using, as well as the
    Python version it supports.

    FIXME: revise this, no longer dependent on CPython 2.7x!
    XXX: Test if CHIPSEC will work uner PyPy.

    required_impl -- implementation name required (eg, 'CPython')
    required_major -- major version required (eg, 2)
    required_minor -- mior version required (eg, 7)

    Return True if what we need, False if something else.

    CHIPSEC module dependency no longer an issue, we can run under CPython3
    at OS-level. But still need to run under CPython2.7x under UEFI. Fix
    code to work with Python3, then remove 2.7x-dependency.
    Test with Jython, PyPy, IronPython, etc.

    Older comment:
    We need CPython version 2.7x for 2 reasons:
    * We need to run CHIPSEC (including under UEFI). CHIPSEC requires CPython
      2.7x. We can workaround this by moving the CPython 2.7-centric CHIPSEC
      code to external code, and spawn external CPython 2.7x to run CHIPSEC,
      so we can run under a different type/version of Python.
    * We need to run in the UEFI Shell environment. The only Python for UEFI
      is CPython 2.7x. Workaround is to port Python 3.x to UEFI, or wait for
      others to port it.
    '''
    if verbose:
        info(required_impl + ' for Python v' +
             str(required_major) + '.' +
             str(required_minor) + ' is required')
    impl = platform.python_implementation()
    if verbose:
        info('Current Python implementation: ' + impl)
    if impl is None:
        error('Current Python implementation name is empty')
        return False
    if impl != required_impl:
        error('Current Python is not the required Python implementation')
        return False
    (major, minor, _, _, _) = sys.version_info
    if verbose:
        info('Current Python version: v' + str(major) + '.' + str(minor))
    if (major != required_major) and (minor != required_minor):
        error('Current Python is not the required Python version')
        return False
    return True


def generate_uuid(hex_style=True, urn_style=False, uuid1=False, uuid4=False,
                  verbose=False):
    '''Generate a UUID and returns a string version of it.

    The generated UUID can be of two types, uuid1 or uuid4.
    The generated UUID can be of two kinds of strings, hex or URN.
    The user must specify the type and string kind.

    hex -- If True generate UUID as a 32-character hexadecimal string.
    urn -- If True, generate UUID as a RFC 4122-style URN-based
           hexadecimal string.
    uuid1 -- If True, generate UUID1-style, based on MAC address
             and current time. Use uuid1 for machine-centric data.
    uuid4 -- If True, generate UUID4-style, based on random data.
             Use uuid4 for machine-independent data.

    Returns specified UUID string, or None if there was an error.
    '''
    if uuid1:
        if verbose:
            info('Generating type1 UUID, based on host ID and current time')
        u = uuid.uuid1()
    elif uuid4:
        if verbose:
            info('Generating type4 UUID, based on random data')
        u = uuid.uuid4()
    else:
        error('Must set either uuid1 or uuid4 to True')
        return None
    if u is None:
        error('Failed to generate UUID')
        return None
    if hex_style:
        if verbose:
            info('Generating hex string representation of UUID')
        return str(u.hex)
    elif urn_style:
        if verbose:
            info('Generating URN string representation of UUID')
        return str(u.urn)
    else:
        error('Must set either hex or urn to True')
        return None


def is_dir_empty(root):
    '''Checks if a directory is empty (no files or subdirs).

    Traverses a directory, counting the number of files and subdirs
    it contains. An empty directory has no subdirs or files in it.

    Returns True if no files or subdirs, False if nonempty or some
    other problem with directory traversal.
    '''
    # XXX Init code checks returning False conflicts with empty logic
    # XXX Downream traverse_dir() code does not handle errors.
    # XXX TOCTOU issues.
    if is_none_or_null(root):
        error('Directory name unspecified')
        return False
    if not dir_exists(root):
        error('Directory does not exist: ' + root)
        return False
    status, dir_count, file_count, file_bytes = traverse_dir(root)
    if (is_none_or_nonbool(status)) and (status is False):
        error('Directory traversal failed')
        return False
    # XXX dir_count and file_count are Lists, not Ints.
    if dir_count is None:
        dir_count = 0
    if file_count is None:
        file_count = 0
    debug('Directory count: ' + str(dir_count))
    debug('File count: ' + str(file_count))
    debug('Bytes used: ' + str(file_bytes))
    if file_bytes > 0:
        error('Directory non-empty: ' + str(file_bytes) + ' bytes used')
        return False
    debug('Directory appears usable')
    return True

#####################################################################

# chipsec.py


def chipsec(toolns, tool, prd, ptd, erc):
    '''Entry point for different toolns values for tool name.'''
    debug('chipsec resolver: toolns=' + toolns + ', tool=' + tool)
    if toolns == 'chipsec_test.bios_keyboard_buffer':
        rc = chipsec_test_bios_kbrd_buffer(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_test.bios_smi':
        rc = chipsec_test_bios_smi(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_test.bios_ts':
        rc = chipsec_test_bios_ts(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_test.bios_wp':
        rc = chipsec_test_bios_wp(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_test.ia32cfg':
        rc = chipsec_test_ia32cfg(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_test.memconfig':
        rc = chipsec_test_memconfig(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_test.remap':
        rc = chipsec_test_remap(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_test.rtclock':
        rc = chipsec_test_rtclock(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_test.secureboot_variables':
        rc = chipsec_test_secureboot_variables(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_test.smm':
        rc = chipsec_test_smm(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_test.smm_dma':
        rc = chipsec_test_smm_dma(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_test.smrr':
        rc = chipsec_test_smrr(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_test.spi_desc':
        rc = chipsec_test_spi_desc(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_test.spi_fdopss':
        rc = chipsec_test_spi_fdopss(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_test.spi_lock':
        rc = chipsec_test_spi_lock(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_test.uefi_access_spec':
        rc = chipsec_test_uefi_access_uefispec(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_test.uefi_s3_bootscript':
        rc = chipsec_test_uefi_s3bootscript(toolns, tool, prd, ptd, erc)
#    elif toolns == 'chipsec_uefi_blacklist':
#        rc = chipsec_uefi_blacklist(toolns, tool, prd, ptd, erc, get_tool_arg(toolns, 'rom_bin_file'))
    elif toolns == 'chipsec_acpi_list':
        rc = chipsec_acpi_list(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_acpi_table':
        rc = chipsec_acpi_table(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_cmos_dump':
        rc = chipsec_cmos_dump(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_cpu_info':
        rc = chipsec_cpu_info(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_cpu_pt':
        rc = chipsec_cpu_pt(toolns, tool, prd, ptd, erc)
#    elif toolns == 'chipsec_decode':
#        rc = chipsec_decode(toolns, tool, prd, ptd, erc, get_tool_arg(toolns, 'spi_bin_file'))
    elif toolns == 'chipsec_decode_types':
        rc = chipsec_decode_types(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_ec_dump':
        rc = chipsec_ec_dump(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_io_list':
        rc = chipsec_io_list(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_iommu_config':
        rc = chipsec_iommu_config(toolns, tool, prd, ptd, erc, chipsec_iommu_engine)
    elif toolns == 'chipsec_iommu_list':
        rc = chipsec_iommu_list(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_iommu_pt':
        rc = chipsec_iommu_pt(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_iommu_status':
        rc = chipsec_iommu_status(toolns, tool, prd, ptd, erc, chipsec_iommu_engine)
    elif toolns == 'chipsec_mmio_list':
        rc = chipsec_mmio_list(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_pci_dump':
        rc = chipsec_pci_dump(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_pci_enumerate':
        rc = chipsec_pci_enumerate(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_pci_xrom':
        rc = chipsec_pci_xrom(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_platform':
        rc = chipsec_platform(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_spd_detect':
        rc = chipsec_spd_detect(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_spd_dump':
        rc = chipsec_spd_dump(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_spidesc':
        rc = chipsec_spidesc(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_spi_dump':
        rc = chipsec_spi_dump(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_spi_info':
        rc = chipsec_spi_info(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_ucode_id':
        rc = chipsec_ucode_id(toolns, tool, prd, ptd, erc)
#    elif toolns == 'chipsec_uefi_decode':
#        rc = chipsec_uefi_decode(toolns, tool, prd, ptd, erc, get_tool_arg(toolns, 'rom_bin_file'))
    elif toolns == 'chipsec_uefi_nvram_auth':
        rc = chipsec_uefi_nvram_auth(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_uefi_nvram':
        rc = chipsec_uefi_nvram(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_uefi_s3_bootscript':
        rc = chipsec_s3bootscript(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_uefi_tables':
        rc = chipsec_uefi_tables(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_uefi_types':
        rc = chipsec_uefi_types(toolns, tool, prd, ptd, erc)
    elif toolns == 'chipsec_uefi_var_list':
        rc = chipsec_uefi_var_list(toolns, tool, prd, ptd, erc)
    else:
        error(tool + ' resolver: no entry found for: ' + toolns)
        return -1
    return rc


def chipsec_test_memconfig(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m memconfig'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'memconfig']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_test_remap(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m remap'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'remap']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_test_smm_dma(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m smm_dma'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'smm_dma']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_test_secureboot_variables(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m common.secureboot.variables [-a modify]'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'common.secureboot.variables']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_test_uefi_access_uefispec(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m common.uefi.access_uefispec'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'common.uefi.access_uefispec']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_test_uefi_s3bootscript(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m common.uefi.s3bootscript [-a <script_address>]'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'common.uefi.s3bootscript']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_test_bios_kbrd_buffer(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m common.bios_kbrd_buffer'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'common.bios_kbrd_buffer']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_test_bios_smi(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m common.bios_smi'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'common.bios_smi']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_test_bios_ts(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m common.bios_ts'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'common.bios_ts']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_test_bios_wp(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m common.bios_wp'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'common.bios_wp']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_test_ia32cfg(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m common.ia32cfg'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'common.ia32cfg']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_test_rtclock(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m common.rtclock'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'common.rtclock']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_test_smm(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m common.smm'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'common.smm']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_test_smrr(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m common.smrr'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'common.smrr']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_test_spi_desc(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m common.spi_desc'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'common.spi_desc']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_test_spi_fdopss(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m common.spi_fdopss'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'common.spi_fdopss']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_test_spi_lock(toolns, tool, prd, ptd, erc):
    '''Call chipsec_main -m common.spi_lock'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-m', 'common.spi_lock']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_uefi_blacklist(toolns, tool, prd, ptd, erc, rom_bin):
    '''Call chipsec_main -i -n -m tools.uefi.blacklist -a uefi.rom,blacklist.json

    The offline version of chipsec_uefi_blacklist uses an existing rom.bin,
    previously generated by a live tool, and checks it against blacklist.
    We don't use the online version. Instead, call chipsec_util SPI Dump
    to gather the live rom.bin, the pass it to this offline code.

    rom_bin -- name of rom.bin file this function creates.
    '''
    # XXX pass 'blacklist.json' file as arg, don't hardcode.
    # XXX Enable way for user to specify their own custom blacklist file.
    # XXX check if chipsec's blacklist file exists. Where?
    # XXX check if any user-specifed blacklist files exist.
    warning('SLOW, calling SPI Dump..')
    blacklist_file = 'blacklist.json'
    if is_none_or_null(rom_bin):
        error('no rom.bin file, needed by blacklist tool')
        # XXX enable live use of blacklist, which creates it's own rom.bin.
        return 1
    if fail_if_missing('chipsec_uefi_blacklist_offline', rom_bin):
        return 1
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_main', '-i', '-n', '-m', 'tools.uefi.blacklist', '-a', ',' + blacklist_file]
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_acpi_list(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util acpi list'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'acpi', 'list']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_acpi_table(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util utility: acpi table acpi_tables.bin'''
    # XXX need another variation for each table:  chipsec_util acpi table <name>
    # XXX for now, dump all ACPI tales to acpi_tables.bin;
    # Later, figure out how to determine which tables the current system has,
    # and create a separate acpi.<name>.bin file for each separate table.
    # XXX how to parse resulting file?
    # XXX learn how to use <name> arg
    # XXX validate input
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'acpi', 'table', 'acpi_tables.bin']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_platform(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util platform'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'platform']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_cmos_dump(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util cmos dump'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'cmos', 'dump']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_cpu_info(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util cpu info'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'cpu', 'info']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_cpu_pt(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util cpu pt'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'cpu', 'pt']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_decode_types(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util decode types to show supported FW_type values.'''
    # XXX save results in a list, for use by offline_chipsec_util_decode()
    # XXX howto determine list, source-time or run-time?
    # XXX for Linux can use SysFS's copy of ACPI tables to get list.
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'decode', 'types']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_decode(toolns, tool, prd, ptd, erc, fw_type, spi_bin):
    '''Call chipsec_util decode <rom> [fw_type]

    Create multiple (?!) log files, binaries, and directories that
    correspond to the sections, firmware volumes, files, variables, etc.
    stored in the SPI flash. CHIPSEC does not autodetect the correct
    format. If the nvram directory doesn't appear, and the list of nvram
    variables is empty, try again with another type.
    '''
    # XXX 'multiple files'?
    # XXX enumerate uefi.fw_types in code, create list in docs.
    # XXX input fw_type is currently unused.
    # XXX How to use fw_type to parse NVRAM variables?
    # XXX append ' ' + fw_type suffix, if specified
    # XXX need a list of valid NVRAM types (static or dynamic)?
    # XXX validate input/output file
    if not path_exists(spi_bin):
        error('Decode failed, file "' + spi_bin + '" missing')
        return 1
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'decode', spi_bin]
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_ec_dump(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util ec dump'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'ec', 'dump']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_io_list(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util io list'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'io', 'list']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_iommu_list(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util iommu list''' 
    # XXX Save results and feed it into 'iommu status'
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'iommu', 'list']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_iommu_status(toolns, tool, prd, ptd, erc, iommu_engine):
    '''Call chipsec_util iommu status [iommu_engine]'''
    # XXX get input iommu_engine from user, or from output of 'iommu list'
    # XXX validate input
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'iommu', 'status', iommu_engine]
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_iommu_config(toolns, tool, prd, ptd, erc, iommu_engine):
    '''Call chipsec_util iommu config [iommu_engine]'''
    # XXX get input iommu_engine from output of 'iommu list'
    # XXX validate input
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'iommu', 'config', iommu_engine]
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_iommu_pt(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util iommu pt'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'iommu', 'pt']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_mmio_list(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util mmio list'''
    # XXX Need a new variation of this command that dumps all valid mmio types from list.
    # XXX need list of MMIO_BAR_names. Static in spec/code or dynamic?
    # XXX use 'mmio dump <MMIO_BAR_name>'
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'mmio', 'list']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_pci_enumerate(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util pci enumerate'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'pci', 'enumerate']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_pci_dump(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util pci dump [<bus> <device> <function>]'''
    # XXX Need another variation of tool that dumps specific bus/device
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'pci', 'dump']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_pci_xrom(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util pci xrom [<bus> <device> <function>] [xrom_address]'''
    # XXX Need another variation of tool that dumps specific bus/device info
    # XXX need to download oprom.bin files for each PCIe device
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-i', '-m', 'chipsec_util', 'pci', 'xrom']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_spd_detect(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util spd detect'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'spd', 'detect']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_spd_dump(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util spd dump [device_addr]'''
    # XXX Need another variation of tool that dumps specific device_addr info?
    # XXX Need a list of interesting spd device addresses. Static or dynamic?
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'spd', 'dump']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_spi_dump(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util spi dump rom.bin

    Generates rom.bin.
    The rom.bin file will contain the full binary of the SPI flash.
    It can then be parsed using the decode util command.
    If slow, use DEBUG or VERBOSE logger options to see progress.
    '''
    filename = 'rom.bin'
    # XXX validate input/output file
    # XXX if rom.bin already exists before running chipsec, warn or abort?
    # XXX then check if file exists and is nonzero.
    # XXX hash rom.bin and publish a few ways
    ign = warn_if_overwriting_file('chipsec_util spi dump', filename)
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'spi', 'dump', filename]
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_spi_info(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util spi info'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'spi', 'info']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_spidesc(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util spidesc spi.bin

    TODO: rename this partial rom.bin something else, for clarity.
    This generated rom.bin is not a complete one, use SPI Dump instead,
    or save this as a separate one, don't overwrite SPI Dump's output.
    '''
    filename = 'spi.bin'
    # XXX create tool_args.chipsec_spidesc_bin,
    # separate from chipsec_spi_bin and rom_bin
    # XXX what file format is spi.bin in? what generated it?
    # XXX is there an online use of this command [that might output to a file]?
    # XXX validate input/output file
    # XXX also run 'spidesc' alternative of this command.
    ign = warn_if_overwriting_file('chipsec_util spidesc', filename)
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'spidesc', filename]
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_ucode_id(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util ucode id'''
    # Need another variation of this tool which calls DECODE
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'ucode', 'id']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_uefi_types(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util uefi types'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'uefi', 'types']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_uefi_var_list(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util uefi var-list'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'uefi', 'var-list']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_uefi_decode(toolns, tool, prd, ptd, erc, rom_bin):
    '''Call chipsec_util uefi decode uefi.rom [fw_type]'''
    # XXX validate input/output file
    # Need FW_TYPE input
    filename = 'uefi.rom'
    if fail_if_missing('chipsec_util uefi decode', filename):
        error('File ' + filename + ' missing, skipping')
        return 1  # XXX  mark as SKIPPED
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'uefi', 'decode', filename]
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_uefi_tables(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util uefi tables'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'uefi', 'tables']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_uefi_keys(toolns, tool, prd, ptd, erc, uefi_keyvar_file):
    '''Call chipsec_util uefi keys db.bin
    File(s) generated:  db.bin (one file of all variables)
    '''
    filename = 'uefi-keyvar.bin'
    # XXX does read a file or generate a file (offline or online?)!
    # XXX validate input/output file
    ign = warn_if_overwriting_file('chipsec_util uefi keys', filename)
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'uefi', 'keys', filename]
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_s3bootscript(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util uefi s3bootscript [script_address]'''
    # XXX add script_address arg (how do you find this address?)
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'uefi', 's3bootscript']
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_uefi_nvram(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util uefi nvram <rom_file> [fw_type]'''
    # Not specifying FW_TYPE add later
    filename = 'nvram.bin'
    # if fw_type is None:
    #     warning('No FW_TYPE specified')
    ign = warn_if_overwriting_file('chipsec_util uefi nvram', filename)
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'uefi', 'nvram', filename]
    return spawn_process(cmd, ptd, erc, toolns)


def chipsec_uefi_nvram_auth(toolns, tool, prd, ptd, erc):
    '''Call chipsec_util uefi nvram[-auth] <rom_file> [fw_type]'''
    # Not specifying FW_TYPE add later
    filename = 'nvram-auth.bin'
    # if fw_type is None:
    #     warning('No FW_TYPE specified')
    ign = warn_if_overwriting_file('chipsec_util uefi nvram-auth', filename)
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = ['python', '-i', '-m', 'chipsec_util', 'uefi', 'nvram-auth', filename]
    return spawn_process(cmd, ptd, erc, toolns)


#####################################################################

# acpica-tools.py
# XXX acpixtract()


def acpidump(toolns, tool, prd, ptd, erc):
    '''Run live command: 'acpidump'.

    Generates multiple <XXXX>.dat files, one per each ACPI table on target
    system. Use acpixtract to do offline analysis of these generated files.
    '''
    # XXX Remove -b, so acpiextract can input them?
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, '-z', '-b']
    return spawn_process(cmd, ptd, erc, toolns)


#####################################################################

# dmidecode.py


def dmidecode(toolns, tool, prd, ptd, erc):
    '''Entry point for different toolns values for tool name.'''
    if not os_is_linux():
        error(tool + ' only works on Linux')
        return -1  # XXX generate exception
    # if toolns == 'dmidecode_install_help':
    #     rc = dmidecode_install_help(toolns, tool, prd, ptd, erc)
    # elif toolns == 'dmidecode_get_version':
    #     rc = dmidecode_get_version(toolns, tool, prd, ptd, erc)
    # elif toolns == 'dmidecode_get_help':
    #     rc = dmidecode_get_help(toolns, tool, prd, ptd, erc)
    if toolns == 'dmidecode_decode':
        rc = dmidecode_decode(toolns, tool, prd, ptd, erc)
    elif toolns == 'dmidecode_dump':
        rc = dmidecode_dump(toolns, tool, prd, ptd, erc)
        # get_tool_arg(toolns, 'dmidecode_bin_file'))
    else:
        error(tool + ' resolver: no entry found for: ' + toolns)
        return -1
    return rc


def dmidecode_decode(toolns, tool, prd, ptd, erc):
    '''Run 'dmidecode' offline command.'''
    filename = 'dmidecode.bin'
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    if not is_none_or_null(filename):
        error('dmidecode_bin_file not specified')
        return -1  # XXX generate exception
    cmd = [tool, '-from-dump', filename]
    return spawn_process(cmd, ptd, erc, toolns)


def dmidecode_dump(toolns, tool, prd, ptd, erc):
    '''Run 'dmidecode' live command.'''
    filename = 'dmidecode.bin'
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, '-dump-bin', filename]
    return spawn_process(cmd, ptd, erc, toolns)


#####################################################################

# flashrom.py


def flashrom(toolns, tool, prd, ptd, erc):
    '''Entry point for different toolns values for tool name.'''
    # if toolns == 'flashrom_install_help':
    #     rc = flashrom_install_help(toolns, tool, prd, ptd, erc)
    # elif toolns == 'flashrom_get_version':
    #     rc = flashrom_get_version(toolns, tool, prd, ptd, erc)
    # elif toolns == 'flashrom_get_help':
    #     rc = flashrom_get_help(toolns, tool, prd, ptd, erc)
    rc = -1
    if toolns == 'flashrom':
#        rc = flashrom_dump_rom(toolns, tool, prd, ptd, erc,
#                      get_tool_arg(toolns, 'rom_bin_file'))
#    else:
        error(tool + ' resolver: no entry found for: ' + toolns)
        return rc
    return rc


def flashrom_dump_rom(toolns, tool, prd, ptd, erc, flashrom_rom_bin_file):
    '''Run 'flashrom' command.'''
    # --list-supported
    # --chip x
    # -read rom.bin -p x

    # flashrom_list_supported
    # --list-supported
    # Output of this needed before you can dump rom.bin

    # flashrom_read_flash
    # --read <file>
    # --programmer <name>

    # --flashrom_device=
    # flashrom_programmer_device_list = [
    # 'internal', 'dummy', 'nic3com', 'nicrealtek', 'gfxnvidia',
    # 'drkaiser', 'satasii', 'atavia', 'it8212', 'ft2232_spi',
    # 'serprog', 'buspirate_spi', 'dediprog', 'rayer_spi',
    # 'pony_spi', 'nicintel', 'nicintel_spi', 'nicintel_eeprom',
    # 'ogp_spi', 'satamv', 'linux_spi', 'usbblaster_spi',
    # 'pickit2_spi', 'ch341a_spi' ]
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    if not os_is_linux():
        error(tool + ' only works on Linux')
        return -1  # XXX generate exception
    if not is_none_or_null(flashrom_rom_bin_file):
        error('flashrom_rom_bin_file not specified')
        return -1  # XXX generate exception
    # XXX how to use flashrom_rom_bin_file?
    cmd = [tool]
    cmd.append('--verbose')  # more verbose output
    # cmd.append('--programmer <name>')  # specify the programmer device.
    # cmd.append('--read <file>')  # read flash and save to <file>
    # cmd.append('--verify <file>')  # verify flash against <file>
    # cmd.append('--chip <chipname>')  # probe only for specified flash chip
    # cmd.append('--output <logfile>')  # log output to <logfile>
    cmd.append('--list-supported')  # print supported devices
    return spawn_process(cmd, ptd, erc, toolns)


#####################################################################

# fwts.py


def fwts(toolns, tool, prd, ptd, erc):
    '''Entry point for different toolns values for tool name.'''
    if not os_is_linux():
        error(tool + ' only works on Linux')
        return -1  # XXX generate exception
    if toolns == 'fwts_version':
        rc = fwts_version(toolns, tool, prd, ptd, erc)
    elif toolns == 'fwts_cpufreq':
        rc = fwts_cpufreq(toolns, tool, prd, ptd, erc)
    elif toolns == 'fwts_maxfreq':
        rc = fwts_maxfreq(toolns, tool, prd, ptd, erc)
    elif toolns == 'fwts_msr':
        rc = fwts_msr(toolns, tool, prd, ptd, erc)
    elif toolns == 'fwts_mtrr':
        rc = fwts_mtrr(toolns, tool, prd, ptd, erc)
    elif toolns == 'fwts_nx':
        rc = fwts_nx(toolns, tool, prd, ptd, erc)
    elif toolns == 'fwts_virt':
        rc = fwts_virt(toolns, tool, prd, ptd, erc)
    elif toolns == 'fwts_aspm':
        rc = fwts_aspm(toolns, tool, prd, ptd, erc)
    elif toolns == 'fwts_dmicheck':
        rc = fwts_dmicheck(toolns, tool, prd, ptd, erc)
    elif toolns == 'fwts_apicedge':
        rc = fwts_apicedge(toolns, tool, prd, ptd, erc)
    elif toolns == 'fwts_klog':
        rc = fwts_klog(toolns, tool, prd, ptd, erc)
    elif toolns == 'fwts_oops':
        rc = fwts_oops(toolns, tool, prd, ptd, erc)
    elif toolns == 'fwts_esrt':
        rc = fwts_esrt(toolns, tool, prd, ptd, erc)
    elif toolns == 'fwts_acpi_tests':
        rc = fwts_acpi_tests(toolns, tool, prd, ptd, erc)
    elif toolns == 'fwts_uefi_tests':
        rc = fwts_uefi_tests(toolns, tool, prd, ptd, erc)
    else:
        error(tool + ' resolver: no entry found for: ' + toolns)
        return -1
    return rc


def fwts_version(toolns, tool, prd, ptd, erc):
    '''Call the FWTS version command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, 'version']
    return spawn_process(cmd, ptd, erc, toolns)


def fwts_cpufreq(toolns, tool, prd, ptd, erc):
    '''Call the FWTS cpufreq command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, 'cpufreq']
    return spawn_process(cmd, ptd, erc, toolns)


def fwts_maxfreq(toolns, tool, prd, ptd, erc):
    '''Call the FWTS maxfreq command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, 'maxfreq']
    return spawn_process(cmd, ptd, erc, toolns)


def fwts_msr(toolns, tool, prd, ptd, erc):
    '''Call the FWTS msr command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, 'msr']
    return spawn_process(cmd, ptd, erc, toolns)


def fwts_mtrr(toolns, tool, prd, ptd, erc):
    '''Call the FWTS mtrr command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, 'mtrr']
    return spawn_process(cmd, ptd, erc, toolns)


def fwts_nx(toolns, tool, prd, ptd, erc):
    '''Call the FWTS nx command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, 'nx']
    return spawn_process(cmd, ptd, erc, toolns)


def fwts_virt(toolns, tool, prd, ptd, erc):
    '''Call the FWTS virt command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, 'virt']
    return spawn_process(cmd, ptd, erc, toolns)


def fwts_aspm(toolns, tool, prd, ptd, erc):
    '''Call the FWTS aspm command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, 'aspm']
    return spawn_process(cmd, ptd, erc, toolns)


def fwts_dmicheck(toolns, tool, prd, ptd, erc):
    '''Call the FWTS dmicheck command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, 'dmicheck']
    return spawn_process(cmd, ptd, erc, toolns)


def fwts_apicedge(toolns, tool, prd, ptd, erc):
    '''Call the FWTS apicedge command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, 'apicedge']
    return spawn_process(cmd, ptd, erc, toolns)


def fwts_klog(toolns, tool, prd, ptd, erc):
    '''Call the FWTS klog command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, 'klog']
    return spawn_process(cmd, ptd, erc, toolns)


def fwts_oops(toolns, tool, prd, ptd, erc):
    '''Call the FWTS oops command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, 'oops']
    return spawn_process(cmd, ptd, erc, toolns)


def fwts_esrt(toolns, tool, prd, ptd, erc):
    '''Call the FWTS esrt command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, 'esrt']
    return spawn_process(cmd, ptd, erc, toolns)


def fwts_uefi_tests(toolns, tool, prd, ptd, erc):
    '''Call the FWTS --uefitests command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, '--uefitests']
    return spawn_process(cmd, ptd, erc, toolns)


def fwts_acpi_tests(toolns, tool, prd, ptd, erc):
    '''Call the FWTS --acpitests command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, '--acpitests']
    return spawn_process(cmd, ptd, erc, toolns)

#####################################################################

# lshw.py


def lshw(toolns, tool, prd, ptd, erc):
    '''Run 'lshw' command.'''
    if not os_is_linux():
        error(tool + ' only works on Linux')
        return -1  # XXX generate exception
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, '-short', '-businfo', '-sanitize', '-notime', '-numeric']
    return spawn_process(cmd, ptd, erc, toolns)

#####################################################################

# lspci.py


def lspci(toolns, tool, prd, ptd, erc):
    '''Entry point for different toolns values for tool name.'''
    if not os_is_linux():
        error(tool + ' only works on Linux')
        return -1  # XXX generate exception
    if toolns == 'lspci_vvnn':
        rc = lspci_vvnn(toolns, tool, prd, ptd, erc)
    elif toolns == 'lspci_xxx':
        rc = lspci_xxx(toolns, tool, prd, ptd, erc)
    else:
        error(tool + ' resolver: no entry found for: ' + toolns)
        return -1
    return rc


def lspci_vvnn(toolns, tool, prd, ptd, erc):
    '''Run 'lspci' command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, '-vvnn']
    return spawn_process(cmd, ptd, erc, toolns)


def lspci_xxx(toolns, tool, prd, ptd, erc):
    '''Run 'lspci' command.'''
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, '-xxx']
    return spawn_process(cmd, ptd, erc, toolns)


#####################################################################

# intel_amt_discovery.py

# Detect Intel SA-00075 aka: CVE-2017-5689 AMT vulnerability


def intel_amt_discovery(toolns, tool, prd, ptd, erc):
    '''Run live command: 'INTEL-SA-00075-Discovery-Tool'.'''
    if not os_is_linux():
        error(tool + ' only works on Linux')
        return -1  # XXX generate exception
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool]
    return spawn_process(cmd, ptd, erc, toolns)

#####################################################################

# intel_me_detection.py

# Detect Intel SA-00086 aka: 
# CVE-2017-5705,CVE-2017-5708,CVE-2017-5711,CVE-2017-5712,CVE-2017-5706,CVE-2017-5707,CVE-2017-5709,CVE-2017-5710,CVE-2017-5706,CVE-2017-5709 
# Intel ME vulnerability

def intel_me_detection(toolns, tool, prd, ptd, erc):
    '''Run live command: ''intel_sa00086.py'.'''
    if not os_is_linux():
        error(tool + ' only works on Linux')
        return -1  # XXX generate exception
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool]
    return spawn_process(cmd, ptd, erc, toolns)

#####################################################################


# lsusb.py


def lsusb(toolns, tool, prd, ptd, erc):
    '''Run live command: 'lsusb'.'''
    if not os_is_linux():
        error(tool + ' only works on Linux')
        return -1  # XXX generate exception
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    cmd = [tool, '-v']
    return spawn_process(cmd, ptd, erc, toolns)


#####################################################################

# pawn.py


def pawn(toolns, tool, prd, ptd, erc):
    '''Run 'pawn' command.'''
    # XXX how to use pawn_rom_bin_file?
    if not os_is_linux():
        error(tool + ' only works on Linux')
        return -1  # XXX generate exception
    info('Executing ' + toolns + ' variation of tool: ' + tool)
    filename = 'rom.bin'
    ign = warn_if_overwriting_file('pawn rom.bin file', filename)
    cmd = [tool, '-v']
    return spawn_process(cmd, ptd, erc, toolns)


#####################################################################

# manifest.py


def create_manifest_file(path):
    '''Create a manifest.txt for all files in a directory.

    Create a manifest.txt file, in the specified directory, and
    for each file in that directory, add one line to the manifest,
    with a line format of: "<hash> + <space> + <filename> + <newline>".

    Returns True if successful, False if an error occurred.'''
    # XXX MULTIPLE ISSUES in create_sidecar_hash_files() are identical to here!
    MANIFEST_FILENAME = 'manifest.txt'
    if path is None:
        error('Directory to create manifest for is null')
        return False
    if not dir_exists(path):
        error('Directory to create manifest for does not exist: ' + path)
        return False
    debug('make_manifest: path = ' + path)
    fn = path + os.sep + MANIFEST_FILENAME  # os.path.join()
    debug('Creating manifest file: ' + fn)
    if path_exists(fn):
        error('Not overwriting existing manifest file: ' + fn)
        return False
    try:

#    buf = None
#    for fn in generated_files:
#        buf += hash_line
#        # calc hash
#        # with open('manifest.txt', 'wt', encodin='utf-8') as f:
#        f = open('manifest.txt', 'wt', encodin='utf-8')
#        f.write(buf)
#        f.close()

        # Open the manifest file
        debug('Opening manifest file: ' + fn)
        m = open(fn, 'wt')  # , encoding='utf-8')  # , errors='strict')
        for root, dirs, files in os.walk(path):
            debug('make_manifest: root dir = ' + root)
            # For each file, write one line to manifest file
            for f in files:
                debug('make_manifest: current file = ' + f)
                joined = os.path.join(path, f)
                debug('make_manifest: current joined file = ' + joined)
                hash_buf = return_hash_str_of_file(joined)
                if is_none_or_null(hash_buf):
                    error('Hash buffer is null')
                    m.close()
                    return False
                debug('make_manifest: hash string: ' + hash_buf)
                manifest_line = hash_buf + ' ' + f + os.linesep
                if is_none_or_null(manifest_line):
                    error('Manifest record line is null!')
                debug('make_manifest: manifest line: ' + manifest_line)
                m.write(manifest_line)
        debug('Closing manifest file')
        m.close()
    except IOError as e:
        critical(e, 'IOError: Failed to create manifest file: ' + fn)
        sys.exc_info()
        return False
    except OSError as e:
        critical(e, 'OSError: Failed to create manifest file: ' + fn)
        sys.exc_info()
        return False
    # XXX propogate status code upstream
    return True


#####################################################################


# The initial main entry point, which calls main().
if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exc_info()
        print('[ERROR] Received KeyboardInterrupt exception in __main__!')
        sys.exit(1)
else:
    print('[ERROR] Module use unsupported currently!')
    sys.exit(1)

# EOF
