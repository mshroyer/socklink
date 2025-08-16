import os
from pathlib import Path
import subprocess

import pytest

from tests.testlib import (
    Sandbox,
    SocketManager,
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
        assert stub.run("get-device-filename", "/dev/tty/1") == "dev+tty+1"

    def test_get_filename_device(self, stub: TsockStub):
        assert stub.run("get-filename-device", "dev+tty+1") == "/dev/tty/1"


class TestSshAuthSock:
    def test_unset(self, sandbox: Sandbox):
        terminal = Terminal(sandbox, login_sock=False)
        assert terminal.get_ssh_auth_sock() is None

    def test_set(self, terminal: Terminal):
        assert terminal.get_ssh_auth_sock() is not None

    def test_tmux_session(
        self, terminal: Terminal, socket_manager: SocketManager, sandbox: Sandbox
    ):
        socket = socket_manager.reserve_unique()
        terminal.run(f"tmux -S {socket}")
        assert terminal.get_ssh_auth_sock() is not None


class TestCommands:
    def test_show_server_link_unset(self, terminal: Terminal, tsock: Path):
        output = terminal.run(f"{tsock} show-server-link", stdout=True)
        assert output == ""

    def test_set_tty_link(self, sandbox: Sandbox, terminal: Terminal, tsock: Path):
        terminal.run(f"{tsock} set-tty-link")
        assert len(os.listdir(sandbox.root / "tmp" / "tsock" / "ttys")) != 0
