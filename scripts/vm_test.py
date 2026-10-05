#!/usr/bin/env python3

"""Orchestrates a VM-based test run

Uses the host system's QEMU installation to run the socklink test suite in a
VM.

"""

import re
import sys
from pathlib import Path

import pexpect

PROJECT = Path(__file__).absolute().parent.parent


def find_qemu_bin() -> Path:
    rhel_qemu_bin = Path("/usr/libexec/qemu-kvm")
    ubuntu_qemu_bin = Path("/usr/bin/qemu-system-x86_64")

    if rhel_qemu_bin.exists():
        return rhel_qemu_bin
    elif ubuntu_qemu_bin.exists():
        return ubuntu_qemu_bin
    else:
        raise RuntimeError("Unable to locate a qemu binary")


ANSI_RE = re.compile(
    r"""
    \x1B                # ESC
    (?:
        [@-Z\\-_]       # 7-bit C1 single-char sequences
      |
        \[ [0-?]* [ -/]* [@-~]   # CSI ... final byte
      |
        \] .*? (?:\x07|\x1B\\)   # OSC ... terminated by BEL or ST
    )
""",
    re.VERBOSE | re.DOTALL,
)


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def run_tests_in_vm(vm: str):
    vm_image = PROJECT / "vms" / f"{vm}.qcow2"
    if not vm_image.exists():
        raise ValueError(f"No such VM image file: {vm_image}")

    socklink_iso = PROJECT / "vms" / "socklink.iso"
    if not socklink_iso.exists():
        raise RuntimeError(f"No such file: {socklink_iso}")

    qemu = pexpect.spawn(
        str(find_qemu_bin()),
        [
            "-machine",
            "q35,accel=kvm",
            "-cpu",
            "host",
            "-m",
            "2G",
            "-netdev",
            "user,id=net0",
            "-device",
            "virtio-net-pci,netdev=net0",
            "-cdrom",
            str(socklink_iso),
            "-drive",
            f"file={vm_image},if=virtio",
            "-display",
            "none",
            "-serial",
            "stdio",
            "-snapshot",
        ],
        encoding="utf-8",
    )
    qemu.logfile_read = sys.stdout

    PROMPT = re.compile(r"[a-zA-Z0-9-@:~]*[#%$] ")

    def read_output() -> str:
        qemu.readline()  # Read command input
        return strip_ansi(qemu.readline()).strip()

    def run(command: str, check: bool = True, timeout: int = -1):
        qemu.sendline(command)
        qemu.expect(PROMPT, timeout=timeout)

        if check:
            qemu.sendline("echo $?")
            code = read_output()
            qemu.expect(PROMPT)

            if int(code) != 0:
                raise RuntimeError(f"Command returned nonzero exit code: {code}")

    qemu.expect("login: ", timeout=300)
    qemu.sendline("root")
    qemu.expect("Password:")
    qemu.sendline("socklink-test")
    qemu.expect(PROMPT)

    # Prevent OpenIndiana in particular from adding a lot of unneeded ANSI
    # control characters to the output for us to handle.
    run("TERM=vt100")

    qemu.sendline("uname")
    uname = read_output()
    qemu.expect(PROMPT)

    run("mkdir /mnt/cdrom", check=False)

    if uname in ("OpenBSD", "NetBSD"):
        run("mount -t cd9660 /dev/cd0a /mnt/cdrom")
    elif uname == "FreeBSD":
        run("mount -t cd9660 /dev/cd0 /mnt/cdrom")
    elif uname == "SunOS":
        qemu.sendline("rmformat -l | sed -En 's/.*\\/dev\\/rdsk\\/(.*)/\\1/p'")
        cdrom = read_output()
        qemu.expect(PROMPT)
        run(f"mount -F hsfs -o ro /dev/dsk/{cdrom} /mnt/cdrom", timeout=60)
    else:
        raise ValueError(f"Unsupported operating system: {uname}")

    run("mkdir ~test/socklink")
    run("cp -pr /mnt/cdrom/* ~test/socklink/")
    run("chown -R test ~test/socklink")
    run("cd ~test/socklink")
    run("su test")
    run("scripts/test.sh", timeout=600)

    # Avoid trailing non-newline output
    print()


def main():
    run_tests_in_vm(sys.argv[1])


if __name__ == "__main__":
    main()
