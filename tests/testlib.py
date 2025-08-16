"""Test helpers"""

import os
from pathlib import Path
import re
import subprocess
import tempfile
from threading import Thread
from time import sleep
from typing import BinaryIO, List, Optional, TextIO, Tuple

import pexpect
import pytest


# A sequence of magic characters to be included in the controlled shell's
# prompt.  When we see this we know the previously issued command has
# completed.
PROMPT_MAGIC = "ThisIsThePrompt"

# Pattern for matching the prompt and the previous command's exit code.
PROMPT_RE = re.compile(f"(\\d+) {PROMPT_MAGIC}")


def get_project_dir() -> Path:
    return Path(os.path.realpath(__file__)).parents[1]


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
        monkeypatch.setenv("TERM", "dumb")
        monkeypatch.setenv("TMUX_TMPDIR", str(root / "tmp" / "tmux"))
        monkeypatch.setenv("TSOCK_TMPDIR", str(root / "tmp"))
        monkeypatch.setenv("TSOCK_LOG", str(root / "tsock.log"))

        monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)
        monkeypatch.delenv("TMUX", raising=False)

        self._setup_dotfiles()
        os.chdir(root)

    def make_unique_file(self, prefix: str, subdir: Optional[str] = None) -> Path:
        """Returns the path to a new, unique file in the sandbox"""

        if subdir is not None:
            dir = self.root / subdir
        else:
            dir = self.root

        fd, filename = tempfile.mkstemp(prefix=prefix, dir=dir)
        os.close(fd)
        return Path(filename)

    def write_debug(self, msg):
        with open(self.root / "debug.txt", "a") as f:
            print(msg, file=f)
            f.flush()

    def _setup_dotfiles(self):
        with open(self.root / "home" / ".bashrc", "a") as f:
            print(f"PS1='$? {PROMPT_MAGIC}\\n'", file=f)

        with open(self.root / "home" / ".tmux.conf", "a") as f:
            print('set -g default-command "/bin/bash"', file=f)


class SocketManager:
    """A container for tmux sockets"""

    sandbox: Sandbox
    _sockets: List[Path]

    def __init__(self, sandbox):
        self.sandbox = sandbox
        self._sockets = []

    def reserve_unique(self) -> Path:
        path = self.sandbox.make_unique_file("tmux-server-")
        path.unlink()
        self._sockets.append(path)
        return path

    def _shutdown(self, socket: Path):
        if socket.exists():
            try:
                subprocess.run(["tmux", "-S", str(socket), "kill-server"], check=True)
            except subprocess.CalledProcessError:
                pass

    def shutdown_all(self):
        for socket in self._sockets:
            self._shutdown(socket)
        self._sockets = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.shutdown_all()


class Terminal:
    """A pexpect-managed terminal running a shell

    Starts a pseudoterminal running the specified shell on initialization, and
    provides an interface to run commands on the shell.

    """

    sandbox: Sandbox
    child: pexpect.spawn
    tty: str
    ssh_auth_sock: Optional[Path]
    _reader_thread: Thread
    _fifo_w: TextIO

    def __init__(
        self,
        sandbox: Sandbox,
        shell: str = "/bin/bash",
        login_sock: bool = True,
    ):
        self.sandbox = sandbox
        self.shell = shell

        self.child = pexpect.spawn(shell, maxread=4096)
        self.child.setecho(False)

        self._output_lines = []

        # Ensure we've drained the output buffer so that the next prompt we
        # see is in response to this command finishing.
        try:
            self.child.read_nonblocking(size=self.child.maxread, timeout=0.1)
        except pexpect.TIMEOUT:
            pass

        self.tty = self.run("tty", stdout=True) or ""

        if login_sock:
            self._setup_login_ssh_auth_sock()

        self.sandbox.write_debug("Finished init")

    def run(self, command: str, stdout: bool = False) -> Optional[str]:
        """Sends a command to the pexpect child

        If stdout is True, the output will be piped to a file and then
        returned as a string.  Otherwise, output is discarded.

        """

        output_txt = self.sandbox.root / "output.txt"

        if stdout:
            # Instead of capturing output with pexpect, pipe it into a file so
            # we don't have to deal with tmux window decorations.
            command = "{} >{}".format(command, output_txt)

        self.child.sendline(command)
        self.sandbox.write_debug(f"command = {command}")
        exit_code = self._wait_for_prompt()

        if exit_code != 0:
            raise TerminalCommandError(exit_code)

        if stdout:
            subprocess.run(["sync"], check=True)
            with open(output_txt, "r") as f:
                return f.read().rstrip("\n")

    def get_ssh_auth_sock(self) -> Optional[str]:
        sock = self.run("echo $SSH_AUTH_SOCK", stdout=True)
        if sock != "":
            return sock

    def _setup_login_ssh_auth_sock(self):
        path = self.sandbox.make_unique_file("auth_sock-", subdir="home")
        self.run(f"SSH_AUTH_SOCK={path}")
        self.run("export SSH_AUTH_SOCK")

    def _wait_for_prompt(self) -> int:
        while True:
            line = self.child.readline().decode("utf-8").rstrip("\n")
            # self.sandbox.write_debug(f'\nline = "{line}"\n')
            m = PROMPT_RE.match(line)
            if m:
                exit_code = int(m.group(1))
                self.sandbox.write_debug(f"exit_code = {exit_code}")
                return exit_code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.child.close(force=True)


class TerminalCommandError(Exception):
    """An error running a command on the terminal."""

    exit_code: int

    def __init__(self, exit_code: int):
        self.exit_code = exit_code
