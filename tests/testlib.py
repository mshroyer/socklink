"""Test helpers"""

import os
from pathlib import Path
import tempfile
from threading import Thread
from time import sleep
from typing import BinaryIO, List, Optional, TextIO, Tuple

import pexpect
import pytest


# A sequence of magic characters to be included in the controlled shell's
# prompt.  When we see this we know the previously issued command has
# completed.
PROMPT_MAGIC = "%-%-%-%"

# Time to sleep between attempts to read, in seconds.
PAUSE_SECONDS = 0.05


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
        monkeypatch.setenv("TMUX_TMPDIR", str(root / "tmp" / "tmux"))
        monkeypatch.delenv("TMUX", raising=False)

        os.mkfifo(root / "output.fifo")

        self._setup_dotfiles()
        os.chdir(root)

    def make_unique_file(self, prefix: str) -> Path:
        """Returns the path to a new, unique file in the sandbox"""

        fd, filename = tempfile.mkstemp(prefix=prefix, dir=self.root)
        os.close(fd)
        return Path(filename)

    def _setup_dotfiles(self):
        with open(self.root / "home" / ".bashrc", "w+") as f:
            print(f'PS1="{PROMPT_MAGIC}\\n"', file=f)


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
    _output_lines: List[str]
    _fifo_w: TextIO

    def __init__(
        self, sandbox: Sandbox, shell: str = "/bin/bash", has_ssh_auth_sock: bool = True
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

        self._output_lines = []

    def run(self, command: str, stdout: bool = False) -> Optional[str]:
        """Sends a command to the pexpect child

        If stdout is True, the output will be piped to a file and then
        returned as a string.  Otherwise, output is discarded.

        """

        if stdout:
            command = "{} >{}".format(command, self.sandbox.root / "output.fifo")

        self.child.sendline(command)
        self._wait_for_prompt()

        if stdout:
            # Even with the fifo we still need to wait to get the completed
            # command's output for some reason.
            sleep(PAUSE_SECONDS)

            output = "\n".join(self._output_lines)
            self._output_lines = []
            return output

    def _wait_for_prompt(self):
        while True:
            line = self.child.readline().decode("utf-8")
            if PROMPT_MAGIC in line:
                return

    def _write_tty_file(self, prefix: str) -> Tuple[str, Path]:
        filename = self.sandbox.make_unique_file(prefix)
        self.child.sendline(f"tty > {filename}")
        sleep(PAUSE_SECONDS)
        with open(filename, "r") as f:
            tty = f.read().rstrip()

        return (tty, filename)

    def _read_fifo(self):
        with open(self.sandbox.root / "output.fifo", "r") as f:
            for line in f:
                line = line.rstrip("\n")
                self._output_lines.append(line)

    def start_reader_thread(self):
        self._reader_thread = Thread(target=self._read_fifo)
        self._reader_thread.start()
        self._fifo_w = open(self.sandbox.root / "output.fifo", "w")

    def stop_reader_thread(self):
        # Generate an EOF for the reader
        self._fifo_w.close()
        self._reader_thread.join()

    def __enter__(self):
        self.start_reader_thread()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.stop_reader_thread()
