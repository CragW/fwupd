#!/usr/bin/env python3
#
# Copyright 2019 Mario Limonciello <mario.limonciello@dell.com>
#
# SPDX-License-Identifier: LGPL-2.1-or-later

import dbus
import os.path
import sys
import tempfile
import gi

try:
    gi.require_version("Fwupd", "2.0")
except ValueError:
    print("Missing gobject-introspection packages.  Try to install gir1.2-fwupd-2.0.")
    sys.exit(1)
from gi.repository import Fwupd  # pylint: disable=wrong-import-position
from simple_client import get_daemon_property, install, check_exists, modify_config
from add_capsule_header import add_header
from firmware_packager import make_firmware_metainfo, create_firmware_cab


class Variables:
    def __init__(self, device_guid, version):
        self.device_guid = device_guid
        self.developer_name = "Dell Inc"
        self.firmware_name = "New firmware"
        self.firmware_summary = "Unknown"
        self.firmware_description = "Unknown"
        self.firmware_homepage = "https://support.dell.com"
        self.contact_info = "Unknown"
        self.release_version = version
        self.release_description = "Unknown"
        self.update_protocol = "org.uefi.capsule"
        self.version_format = "dell-bios"


def parse_args():
    """Parse arguments for this client"""
    import argparse

    parser = argparse.ArgumentParser(description="Interact with fwupd daemon")
    parser.add_argument("exe", nargs="?", help="exe file")
    parser.add_argument("deviceid", nargs="?", help="DeviceID to operate on(optional)")
    args = parser.parse_args()
    return args


def generate_cab(infile, directory, guid, version):
    output = os.path.join(directory, "firmware.bin")
    ret = add_header(infile, output, guid)
    if ret:
        sys.exit(ret)
    variables = Variables(guid, version)
    make_firmware_metainfo(variables, directory)
    create_firmware_cab(variables, directory)
    cab = os.path.join(directory, "firmware.cab")
    print(f"Generated CAB file {cab}")
    return cab


def find_uefi_device(client, deviceid):
    devices = client.get_devices()
    for item in devices:
        # match the device we were given
        if deviceid:
            if item.get_id() != deviceid:
                continue
        # internal
        if not item.has_flag(Fwupd.DeviceFlags.INTERNAL):
            continue
        # needs reboot
        if not item.has_flag(Fwupd.DeviceFlags.NEEDS_REBOOT):
            continue
        # return the first hit for UEFI plugin
        if item.get_plugin() == "uefi" or item.get_plugin() == "uefi_capsule":
            print(f"Installing to {item.get_name()}")
            return item.get_guid_default(), item.get_id(), item.get_version()
    print("Couldn't find any UEFI devices")
    sys.exit(1)


def set_conf_only_trusted(client, setval):
    prop = "OnlyTrusted"
    current_val = get_daemon_property(prop)
    if current_val:
        pass
    elif setval:
        pass
    else:
        return False
    modify_config(client, "fwupd", prop, str(setval).lower())
    return get_daemon_property(prop) == setval


def prompt_reboot():
    print("An update requires a reboot to complete")
    while True:
        res = input("Restart now? (Y/N) ")
        if res.lower() == "n":
            print("Reboot your machine manually to finish the update.")
            break
        if res.lower() != "y":
            continue
        # reboot using logind
        obj = dbus.SystemBus().get_object(
            "org.freedesktop.login1", "/org/freedesktop/login1"
        )
        obj.Reboot(True, dbus_interface="org.freedesktop.login1.Manager")


if __name__ == "__main__":
    ARGS = parse_args()
    CLIENT = Fwupd.Client()
    check_exists(ARGS.exe)
    try:
        is_restore_required = set_conf_only_trusted(CLIENT, False)
        directory = tempfile.mkdtemp()
        guid, deviceid, version = find_uefi_device(CLIENT, ARGS.deviceid)
        cab = generate_cab(ARGS.exe, directory, guid, version)
        install(CLIENT, cab, deviceid, True, True)
    except Exception as e:
        print(e)

    if is_restore_required:
        set_conf_only_trusted(CLIENT, True)
    prompt_reboot()
