import os
from pathlib import Path
import subprocess

import pytest

from tests.testlib import (
    Sandbox,
    Terminal,
    TerminalCommandError,
    TsockStub,
)


class TestLib:
    def test_error(self, terminal: Terminal):
        with pytest.raises(TerminalCommandError):
            terminal.run("false")


class TestFunctions:
    def test_get_device_filename(self, stub: TsockStub):
        assert stub.run("get-device-filename", "/dev/pts/12") == "dev+pts+12"

    def test_get_filename_device(self, stub: TsockStub):
        assert stub.run("get-filename-device", "dev+pts+12") == "/dev/pts/12"


class TestSshAuthSock:
    def test_unset(self, sandbox: Sandbox):
        terminal = Terminal(sandbox, login_sock=False)
        assert terminal.get_auth_sock() is None

    def test_set(self, terminal: Terminal):
        assert terminal.get_auth_sock() is not None

    def test_tmux_session(self, sandbox: Sandbox, terminal: Terminal):
        socket = sandbox.reserve_tmux_socket()
        terminal.run(f"tmux -S {socket}")
        assert terminal.get_auth_sock() is not None


class TestCommands:
    def test_show_server_link_unset(self, terminal: Terminal, tsock: Path):
        output = terminal.run(f"{tsock} show-server-link", stdout=True)
        assert output == ""

    def test_set_tty_link(self, sandbox: Sandbox, terminal: Terminal, tsock: Path):
        terminal.run(f"{tsock} set-tty-link")
        ttys_dir = sandbox.root / "tmp" / "tsock" / "ttys"
        tty_socks = os.listdir(ttys_dir)
        assert len(tty_socks) == 1
        assert terminal.is_login_auth_sock(ttys_dir / tty_socks[0])


class TestInstallation:
    def test_has_tsock_installation_section_absent(
        self, sandbox: Sandbox, stub: TsockStub
    ):
        rc_file = sandbox.root / "test_rc_file"
        with open(rc_file, "w") as f:
            print(r"echo hello", file=f)

        with pytest.raises(subprocess.CalledProcessError):
            stub.run("has-tsock-installation-section", rc_file)

    def test_has_tsock_installation_section_present(
        self, sandbox: Sandbox, stub: TsockStub
    ):
        rc_file = sandbox.root / "test_rc_file"
        with open(rc_file, "w") as f:
            print(
                "\n".join(
                    [
                        r"echo hello",
                        r"",
                        r"### TSOCK INSTALLATION BEGIN",
                        r"echo tsock",
                        r"### TSOCK INSTALLATION END",
                        r"",
                    ]
                ),
                file=f,
            )

        stub.run("has-tsock-installation-section", rc_file)
