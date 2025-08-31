"""Test helpers"""

from datetime import timedelta
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import List, Optional, TextIO

import pexpect
import pytest


# A sequence of magic characters to be included in the controlled shell's
# prompt.  When we see this we know the previously issued command has
# completed.
PROMPT_MAGIC = "ThisIsThePrompt"

# Pattern for matching the prompt and the previous command's exit code.
PROMPT_RE = re.compile(f".*{re.escape(PROMPT_MAGIC)} (\\d+).*")


def get_project_dir() -> Path:
    return Path(os.path.realpath(__file__)).parents[1]


def resolve_symlink(link: Optional[Path]) -> Optional[Path]:
    """Resolves the file ultimately pointed to by a symlink

    Returns None if the target file doesn't exist.

    """

    if link is None:
        return None

    target = link.resolve()
    if target.exists():
        return target
    else:
        return None


class Sandbox:
    """A sandbox for running a test case

    Represents a dedicated directory tree and configurations of HOME and other
    environment variables.

    """

    monkeypatch: pytest.MonkeyPatch
    root: Path
    _tmux_sockets: List[Path]

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch):
        self.monkeypatch = monkeypatch
        self.root = root
        self._tmux_sockets = []

        (root / "home").mkdir()
        (root / "tmp").mkdir()

        monkeypatch.setenv("HOME", str(root / "home"))
        monkeypatch.setenv("TERM", "xterm")
        monkeypatch.setenv("TMUX_TMPDIR", str(root / "tmp" / "tmux"))
        monkeypatch.setenv("SOCKLINK_DIR", str(root / "tmp" / "socklink"))
        monkeypatch.setenv("SOCKLINK_LOG", str(root / "socklink.log"))

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

    def reserve_tmux_socket(self) -> Path:
        path = self.make_unique_file("tmux-server-")
        path.unlink()
        self._tmux_sockets.append(path)
        return path

    def _shutdown_tmux_socket(self, socket: Path):
        if socket.exists():
            try:
                subprocess.run(["tmux", "-S", str(socket), "kill-server"], check=True)
            except subprocess.CalledProcessError:
                pass

    def shutdown_all_tmux_sockets(self):
        for socket in self._tmux_sockets:
            self._shutdown_tmux_socket(socket)
        self._tmux_sockets = []

    def _setup_dotfiles(self):
        with open(self.root / "home" / ".bashrc", "a") as f:
            print(f"PS1='\\n{PROMPT_MAGIC} $?:\\n\\n'", file=f)

        with open(self.root / "home" / ".zshrc", "a") as f:
            print(f"PROMPT=$'\\n{PROMPT_MAGIC} %?:\\n\\n'", file=f)

        shell = os.getenv("TEST_SHELL") or "bash"
        with open(self.root / "home" / ".tmux.conf", "a") as f:
            print(f'set -g default-command "{shell}"', file=f)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.shutdown_all_tmux_sockets()


class Term:
    """A pexpect-managed terminal running a shell

    Starts a pseudoterminal running the specified shell on initialization, and
    provides an interface to run commands on the shell.

    """

    name: str
    sandbox: Sandbox
    child: pexpect.spawn
    tty: str
    login_auth_sock: Optional[Path]
    _fifo_w: TextIO

    def __init__(
        self,
        name: str,
        sandbox: Sandbox,
        login_sock: bool = True,
    ):
        self.name = name
        self.sandbox = sandbox
        self.shell = os.getenv("TEST_SHELL") or "bash"
        self.debug_filename = f"{name}-debug.txt"

        if login_sock:
            self._setup_login_auth_sock()
        else:
            sandbox.monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)

        self._write_debug(f"Spawning shell {self.shell}")
        self.child = pexpect.spawn(self.shell, maxread=4096)

        self._output_lines = []
        self._drain_read_buffer()

        self.tty = self.run("tty", stdout=True) or ""

        self._write_debug("Finished init")

    def run(
        self, command: str, stdout: bool = False, stderr: bool = True
    ) -> Optional[str]:
        """Sends a command to the pexpect child

        If stdout is True, the output will be piped to a file and then
        returned as a string.  Otherwise, output is discarded.

        """

        stdout_txt = self.sandbox.root / f"{self.name}-stdout.txt"
        stdout_txt.unlink(missing_ok=True)
        stderr_txt = self.sandbox.root / f"{self.name}-stderr.txt"
        stderr_txt.unlink(missing_ok=True)

        # Instead of capturing output with pexpect, pipe it into a file so we
        # don't have to deal with tmux window decorations.
        if stderr:
            command = f"{command} 2> >(tee '{stderr_txt}.tmp' >&2 && mv '{stderr_txt}.tmp' '{stderr_txt}')"
        if stdout:
            command = f"{command} > >(tee '{stdout_txt}.tmp' && mv '{stdout_txt}.tmp' '{stdout_txt}')"

        self._drain_read_buffer()
        self._write_debug(f"command = {command}")
        self.child.sendline(command)

        exit_code = self._wait_for_prompt()

        if exit_code != 0:
            raise TermCommandError(
                exit_code, self._read_output(stderr_txt).rstrip("\n") if stderr else ""
            )

        if exit_code == 0 and stdout:
            return self._read_output(stdout_txt).rstrip("\n")

        self._write_debug("")

    @staticmethod
    def _read_output(path: Path) -> str:
        poll_interval = timedelta(milliseconds=25)
        max_wait = timedelta(seconds=2)
        start = time.monotonic()

        while True:
            try:
                return path.read_text()
            except FileNotFoundError as e:
                now = time.monotonic()
                if (now - start) > max_wait.total_seconds():
                    raise e
                time.sleep(poll_interval.total_seconds())

    def _wait_for_prompt(self) -> int:
        self.child.expect(PROMPT_MAGIC + r" (\d+):")
        return int(self.child.match.group(1))

    def _drain_read_buffer(self):
        # Ensure we've drained the output buffer so that the next prompt we
        # see is in response to this command finishing.
        try:
            while True:
                bs = self.child.read_nonblocking(size=self.child.maxread, timeout=0.1)
                self._write_debug(f"drained {len(bs)} bytes from read buffer")
        except pexpect.TIMEOUT:
            pass

    def get_auth_sock(self) -> Optional[Path]:
        """Gets the current value of SSH_AUTH_SOCK in the active shell

        Note that this issues a command on the shell, so it may change state
        if you have socklink.sh attached to shell hooks.

        """

        sock = self.run("echo $SSH_AUTH_SOCK", stdout=True)
        if sock is not None and sock != "":
            return Path(sock)

    def _setup_login_auth_sock(self):
        self.login_auth_sock = self.sandbox.root / "home" / f"{self.name}-auth_sock"
        self.login_auth_sock.touch()
        self._write_debug(f"login_auth_sock: {self.login_auth_sock}")
        self.sandbox.monkeypatch.setenv("SSH_AUTH_SOCK", str(self.login_auth_sock))

    def _write_debug(self, msg):
        with open(self.sandbox.root / self.debug_filename, "a") as f:
            print(msg, file=f)
            f.flush()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.child.close(force=True)


class TermCommandError(Exception):
    """An error running a command on the terminal."""

    exit_code: int
    stderr: str

    def __init__(self, exit_code: int, stderr: str):
        self.exit_code = exit_code
        self.stderr = stderr


class SocklinkStub:
    """An instance of the socklink script that can be invoked directly"""

    path: Path

    def __init__(self, path: Path, sandbox: Sandbox):
        self.path = path

        # Enable access to test-only functions
        sandbox.monkeypatch.setenv("SOCKLINK_TESTONLY_COMMANDS", "1")

    def run(self, *args: str | Path, stdin: Optional[str] = None) -> str:
        """Run a socklink.sh subcommand and return its stdout

        Runs the subcommand directly, without constructing a sandboxed
        environment.

        """

        in_bytes = stdin.encode("utf-8") if stdin is not None else None
        return (
            subprocess.check_output([self.path] + list(map(str, args)), input=in_bytes)
            .decode("utf-8")
            .rstrip()
        )

    def run_test(self, *args: str | Path, stdin: Optional[str] = None) -> bool:
        """Runs a socklink.sh subcommand and interprets success as a boolean"""

        try:
            self.run(*args, stdin=stdin)
            return True
        except subprocess.CalledProcessError:
            return False


def fail_with_subprocess_error(e: subprocess.CalledProcessError):
    lines = [f"Command {e.cmd!r} exited with return code {e.returncode}"]

    if getattr(e, "stdout", None):
        out = (
            e.stdout if isinstance(e.stdout, str) else e.stdout.decode(errors="ignore")
        )
        if out:
            lines.append("=== STDOUT ===")
            lines.append(out.rstrip())

    if getattr(e, "stderr", None):
        err = (
            e.stderr if isinstance(e.stderr, str) else e.stderr.decode(errors="ignore")
        )
        if err:
            lines.append("=== STDERR ===")
            lines.append(err.rstrip())

    msg = "\n".join(lines)

    # Suppress the default Python stack trace output
    pytest.fail(msg, pytrace=False)
