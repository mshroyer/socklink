"""Test helpers"""

import os
from pathlib import Path
import tempfile
from time import sleep
from typing import Optional, Tuple

import pexpect
import pytest


# Time to wait between attempts to read, in seconds.
TIME_EPSILON = 0.1


class Sandbox:
    """A sandbox for running a test case

    Represents a dedicated directory tree and configurations of HOME and other
    environment variables.

    """

    monkeypatch: pytest.MonkeyPatch
    root: Path

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch):
        self.monkeypatch = monkeypatch
        self.root = root

        (root / "home").mkdir()
        (root / "tmp").mkdir()

        monkeypatch.setenv("HOME", str(root / "home"))
        monkeypatch.setenv("TERM", "xterm")
        monkeypatch.delenv("TMUX", raising=False)

        os.chdir(root)


class Terminal:
    """A pexpect-managed terminal running a shell"""

    sandbox: Sandbox
    child: pexpect.spawn
    tty: str
    ssh_auth_sock: Optional[Path]

    def __init__(
        self, sandbox: Sandbox, shell: str = "/bin/sh", has_ssh_auth_sock: bool = True
    ):
        self.sandbox = sandbox
        self.shell = shell

        self.child = pexpect.spawn(shell)
        self.child.setecho(False)

        tty, tty_file = self._write_tty_file(
            "auth_sock-" if has_ssh_auth_sock else "tty-"
        )
        self.tty = tty
        if has_ssh_auth_sock:
            self.ssh_auth_sock = tty_file
        else:
            self.ssh_auth_sock = None

    def send_command(self, command: str, pipe_output: bool = False) -> Optional[str]:
        """Sends a command to the pexpect child

        If pipe_output is True, the output will be piped to a file and then
        returned as a string.  Otherwise, output is discarded.

        """

        if pipe_output:
            command = "{} > {}".format(command, self.sandbox.root / "output.txt")

        self.child.sendline(command)
        self._read_all()

        if pipe_output:
            with open(self.sandbox.root / "output.txt", "r") as f:
                return f.read().rstrip()

    def _read_all(self):
        while True:
            try:
                self.child.read_nonblocking(size=1024, timeout=TIME_EPSILON)
            except pexpect.TIMEOUT:
                break

    def _write_tty_file(self, prefix: str) -> Tuple[str, Path]:
        filename = self._reserve_file(prefix)
        self.child.sendline(f"tty > {filename}")
        sleep(TIME_EPSILON)
        with open(filename, "r") as f:
            tty = f.read().rstrip()

        return (tty, filename)

    def _reserve_file(self, prefix: str) -> Path:
        fd, filename = tempfile.mkstemp(prefix=prefix, dir=self.sandbox.root)
        os.close(fd)
        return Path(filename)
