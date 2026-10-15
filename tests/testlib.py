"""Test helpers"""

import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

import pexpect
import pytest

# A sequence of magic characters to be included in the controlled shell's
# prompt.  When we see this we know the previously issued command has
# completed.
PROMPT_MAGIC = "ThisIsThePrompt"

# Pattern for matching the prompt and the previous command's exit code.
PROMPT_RE = re.compile(f".*{re.escape(PROMPT_MAGIC)} (\\d+).*")

# Printed along with a unique per-command token and exit status after each
# command run by Term.  Unlike the prompt, which tmux may redraw at any time
# (e.g. when a client attaches or the window is resized), this lets us tell
# exactly which command has finished.
DONE_MAGIC = "ThisCommandIsDone"


def get_project_dir() -> Path:
    return Path(os.path.realpath(__file__)).parents[1]


def resolve_symlink(link: Path | None) -> Path | None:
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
    _tmux_sockets: list[Path]

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

    def make_unique_file(self, prefix: str, subdir: str | None = None) -> Path:
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
    login_auth_sock: Path | None
    _seq: int
    _tmux_tokens: list[str]

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
        self._seq = 0
        self._tmux_tokens = []

        self.login_auth_sock = None
        if login_sock:
            self._setup_login_auth_sock()
        else:
            sandbox.monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)

        self._write_debug(f"Spawning shell {self.shell}")
        self.child = pexpect.spawn(self.shell, maxread=4096)

        self._drain_read_buffer()

        self.tty = self.run("tty", stdout=True) or ""

        self._write_debug("Finished init")

    def run(
        self, command: str, stdout: bool = False, stderr: bool = True
    ) -> str | None:
        """Sends a command to the pexpect child and waits for it to finish

        If stdout is True, the output will be redirected to a file and then
        returned as a string.  Otherwise, it goes to the terminal.

        Don't use this for commands that enter or leave a tmux client; use
        enter_tmux() and exit_tmux() instead.

        """

        token, stdout_txt, stderr_txt = self._next_command()
        command = self._wrap_command(
            command,
            stdout_txt if stdout else None,
            stderr_txt if stderr else None,
            token,
        )

        self._write_debug(f"command = {command}")
        self.child.sendline(command)

        exit_code = self._wait_for_done(token)

        # Also wait for the subsequent prompt, so that any prompt hooks have
        # finished running before we return.
        self._wait_for_prompt()

        if exit_code != 0:
            raise TermCommandError(
                exit_code, stderr_txt.read_text().rstrip("\n") if stderr else ""
            )

        self._write_debug("")
        if stdout:
            return stdout_txt.read_text().rstrip("\n")

    def enter_tmux(self, command: str):
        """Runs a tmux command that attaches this terminal as a client

        Returns once the shell in the attached tmux pane is ready to accept
        commands.

        """

        token, _, stderr_txt = self._next_command()
        command = self._wrap_command(command, None, stderr_txt, token)

        self._write_debug(f"tmux command = {command}")
        self.child.sendline(command)

        # Any prompt seen now must have been drawn by tmux, though it may be a
        # redraw of existing pane contents rather than a fresh prompt.  Either
        # way, it means the client is up and will forward our input to the
        # pane, which we then sync with by running a no-op command there.
        done_re = self._done_re(token)
        i = self.child.expect([PROMPT_MAGIC + r" (\d+):", done_re])
        if i == 1:
            raise TermCommandError(
                int(self.child.match.group(1)), stderr_txt.read_text().rstrip("\n")
            )

        self._tmux_tokens.append(token)
        self.run(":")

    def exit_tmux(self, command: str = "tmux detach"):
        """Runs a command in tmux that causes this terminal's client to exit

        Waits for the tmux command previously run by enter_tmux() to finish.

        """

        token = self._tmux_tokens.pop()

        self._write_debug(f"exit tmux command = {command}")
        self.child.sendline(command)

        exit_code = self._wait_for_done(token)
        self._wait_for_prompt()

        if exit_code != 0:
            stderr_txt = self.sandbox.root / f"{token}-stderr.txt"
            raise TermCommandError(exit_code, stderr_txt.read_text().rstrip("\n"))

    def _next_command(self) -> tuple[str, Path, Path]:
        self._seq += 1
        token = f"{self.name}-{self._seq}"
        return (
            token,
            self.sandbox.root / f"{token}-stdout.txt",
            self.sandbox.root / f"{token}-stderr.txt",
        )

    @staticmethod
    def _wrap_command(
        command: str, stdout_txt: Path | None, stderr_txt: Path | None, token: str
    ) -> str:
        # Redirect straight to files rather than through pipes, so that when
        # the shell gets to the printf the output is complete, regardless of
        # whether something else (e.g. a backgrounded process or the tmux
        # server) is still holding onto the command's stdout or stderr.
        #
        # The printf's format string splits DONE_MAGIC from the token so that
        # the terminal's echo of the command line itself doesn't match.
        if stdout_txt is not None:
            command = f"{{ {command}; }} >{shlex.quote(str(stdout_txt))}"
        if stderr_txt is not None:
            command = f"{{ {command}; }} 2>{shlex.quote(str(stderr_txt))}"
        return f"{command}; printf '\\n%s%s %s\\n' {DONE_MAGIC} {token} \"$?\""

    @staticmethod
    def _done_re(token: str) -> str:
        return re.escape(DONE_MAGIC + token) + r" (\d+)"

    def _wait_for_done(self, token: str) -> int:
        self.child.expect(self._done_re(token))
        return int(self.child.match.group(1))

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

    def get_auth_sock(self) -> Path | None:
        """Gets the current value of SSH_AUTH_SOCK in the active shell

        Note that this issues a command on the shell, so it may change state
        if you have socklink.sh attached to shell hooks.

        """

        sock = self.run("echo $SSH_AUTH_SOCK", stdout=True)
        if sock is not None and sock != "":
            return Path(sock)

    def close(self):
        # When clients disconnect by SSH, their authentication sockets go
        # away, so let's mirror that behavior here.
        if self.login_auth_sock is not None:
            self.login_auth_sock.unlink(missing_ok=True)

        self.child.close(force=True)

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
        self.close()


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

    def run(self, *args: str | Path | int, stdin: str | None = None) -> str:
        """Run a socklink.sh subcommand and return its stdout

        Runs the subcommand directly, without constructing a sandboxed
        environment.

        """

        in_bytes = stdin.encode("utf-8") if stdin is not None else None
        return (
            subprocess.check_output(
                [self.path] + list(map(str, args)),
                input=in_bytes,
                stderr=subprocess.STDOUT,
            )
            .decode("utf-8")
            .rstrip()
        )

    def run_test(self, *args: str | Path, stdin: str | None = None) -> bool:
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
