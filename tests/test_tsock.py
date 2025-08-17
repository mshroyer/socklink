import os
from pathlib import Path
from textwrap import dedent

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
    def test_set_section_no_file(self, sandbox: Sandbox, stub: TsockStub):
        rc_file = sandbox.root / "test_rc_file"
        stub.run(
            "set-tsock-section",
            rc_file,
            stdin=dedent("""\
        foo
        bar
        """),
        )

        assert rc_file.read_text() == dedent("""\
        ### TSOCK INSTALLATION BEGIN
        foo
        bar
        ### TSOCK INSTALLATION END
        """)

    def test_set_section_empty_file(self, sandbox: Sandbox, stub: TsockStub):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.touch()
        stub.run(
            "set-tsock-section",
            rc_file,
            stdin=dedent("""\
        foo
        bar
        """),
        )

        assert rc_file.read_text() == dedent("""\
        ### TSOCK INSTALLATION BEGIN
        foo
        bar
        ### TSOCK INSTALLATION END
        """)

    def test_set_section_empty_section(self, sandbox: Sandbox, stub: TsockStub):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.write_text(
            dedent("""\
        ### TSOCK INSTALLATION BEGIN
        ### TSOCK INSTALLATION END
        """)
        )
        stub.run(
            "set-tsock-section",
            rc_file,
            stdin=dedent("""\
        foo
        bar
        """),
        )

        assert rc_file.read_text() == dedent("""\
        ### TSOCK INSTALLATION BEGIN
        foo
        bar
        ### TSOCK INSTALLATION END
        """)

    def test_set_section_not_preeixsting(self, sandbox: Sandbox, stub: TsockStub):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.write_text(
            dedent("""\
            This is a test
            The remainder of this file should be unmodified.
            """)
        )
        stub.run(
            "set-tsock-section",
            rc_file,
            stdin=dedent("""\
            foo
            bar
            """),
        )

        assert rc_file.read_text() == dedent("""\
            This is a test
            The remainder of this file should be unmodified.

            ### TSOCK INSTALLATION BEGIN
            foo
            bar
            ### TSOCK INSTALLATION END
            """)

    def test_set_section_preserves_rest(self, sandbox: Sandbox, stub: TsockStub):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.write_text(
            dedent("""\
            This is a test

            ### TSOCK INSTALLATION BEGIN
            ### TSOCK INSTALLATION END
            The remainder of this file should be unmodified.
            """)
        )
        stub.run(
            "set-tsock-section",
            rc_file,
            stdin=dedent("""\
            foo
            bar
            """),
        )

        assert rc_file.read_text() == dedent("""\
            This is a test

            ### TSOCK INSTALLATION BEGIN
            foo
            bar
            ### TSOCK INSTALLATION END
            The remainder of this file should be unmodified.
            """)

    def test_has_manual_config_head(self, sandbox: Sandbox, stub: TsockStub):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.write_text(
            dedent("""\
            tsock.sh set-tty-link
            ### TSOCK INSTALLATION BEGIN
            echo foo
            ### TSOCK INSTALLATION END
            echo bar
            """)
        )
        assert stub.run_test("has-manual-config", rc_file)

    def test_has_manual_config_installation(self, sandbox: Sandbox, stub: TsockStub):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.write_text(
            dedent("""\
            echo foo
            ### TSOCK INSTALLATION BEGIN
            tsock.sh set-tty-link
            ### TSOCK INSTALLATION END
            echo bar
            """)
        )
        assert not stub.run_test("has-manual-config", rc_file)

    def test_has_manual_config_tail(self, sandbox: Sandbox, stub: TsockStub):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.write_text(
            dedent("""\
            echo foo
            ### TSOCK INSTALLATION BEGIN
            echo bar
            ### TSOCK INSTALLATION END
            tsock.sh show-server-link
            """)
        )
        assert stub.run_test("has-manual-config", rc_file)
