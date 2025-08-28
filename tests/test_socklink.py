import os
from pathlib import Path
from textwrap import dedent
from time import sleep

import pytest

from tests.plugin import MakeTerm
from tests.testlib import (
    Sandbox,
    Term,
    TermCommandError,
    SocklinkStub,
    resolve_symlink,
)


def delay():
    """Wait some amount of time in hopes tmux hooks have settled"""

    sleep(0.25)


class TestLib:
    def test_error(self, term: Term):
        with pytest.raises(TermCommandError):
            term.run("false")


class TestFunctions:
    def test_get_device_filename(self, stub: SocklinkStub):
        assert stub.run("get-device-filename", "/dev/pts/12") == "dev+pts+12"

    def test_get_filename_device(self, stub: SocklinkStub):
        assert stub.run("get-filename-device", "dev+pts+12") == "/dev/pts/12"


class TestFeatureChecks:
    def test_client_active_hook(self, stub: SocklinkStub):
        assert not stub.run_test("has-client-active-hook", "tmux 3.2")
        assert stub.run_test("has-client-active-hook", "tmux 3.3")

        # Debian 12
        assert stub.run_test("has-client-active-hook", "tmux 3.3a")

        # AlmaLinux 10
        assert stub.run_test("has-client-active-hook", "tmux next-3.4")

        # OpenBSD
        assert not stub.run_test("has-client-active-hook", "tmux openbsd-7.0")
        assert stub.run_test("has-client-active-hook", "tmux openbsd-7.7")


class TestSshAuthSock:
    def test_unset(self, make_term: MakeTerm):
        term = make_term(login_sock=False)
        assert term.get_auth_sock() is None

    def test_set(self, term: Term):
        assert term.get_auth_sock() is not None

    def test_tmux_session(self, sandbox: Sandbox, term: Term):
        socket = sandbox.reserve_tmux_socket()
        term.run(f"tmux -S {socket}")
        assert term.get_auth_sock() is not None

    def test_default_setup(
        self, tmux_sock: Path, make_term: MakeTerm, stub: SocklinkStub
    ):
        stub.run("setup")

        # When testing setup, we have to explicilty make the terminal after
        # running setup so that its newly-setup login shell hooks run.
        term = make_term()
        term.run(f"tmux -S {tmux_sock}")

        auth_sock = term.get_auth_sock()
        assert resolve_symlink(auth_sock) == term.login_auth_sock

    def test_second_concurrent_client(
        self, tmux_sock: Path, make_term: MakeTerm, stub: SocklinkStub
    ):
        stub.run("setup")

        term1 = make_term(login_sock=True)
        term1.run(f"tmux -S {tmux_sock}")
        auth_sock = term1.get_auth_sock()
        delay()
        assert resolve_symlink(auth_sock) == term1.login_auth_sock

        term2 = make_term(login_sock=True)
        term2.run(f"tmux -S {tmux_sock} attach")
        assert auth_sock == term2.get_auth_sock()
        delay()

        # Attaching a second client should immediately redirect the server
        # link to the new client
        assert resolve_symlink(auth_sock) != term1.login_auth_sock
        assert resolve_symlink(auth_sock) == term2.login_auth_sock

    def test_switching_connected_cilent(
        self, tmux_sock: Path, make_term: MakeTerm, stub: SocklinkStub
    ):
        stub.run("setup")

        term1 = make_term(login_sock=True)
        term1.run(f"tmux -S {tmux_sock}")
        auth_sock = term1.get_auth_sock()
        assert resolve_symlink(auth_sock) == term1.login_auth_sock
        term1.run("tmux detach")

        term2 = make_term(login_sock=True)
        term2.run(f"tmux -S {tmux_sock} attach")
        delay()
        assert resolve_symlink(auth_sock) == term2.login_auth_sock
        term2.run("tmux detach")

        term1.run(f"tmux -S {tmux_sock} attach")
        delay()
        assert resolve_symlink(auth_sock) == term1.login_auth_sock

    def test_switching_active_client(
        self, tmux_sock: Path, make_term: MakeTerm, stub: SocklinkStub
    ):
        stub.run("setup")

        term1 = make_term(login_sock=True)
        term1.run(f"tmux -S {tmux_sock}")
        auth_sock = term1.get_auth_sock()
        assert resolve_symlink(auth_sock) == term1.login_auth_sock

        term2 = make_term(login_sock=True)
        term2.run(f"tmux -S {tmux_sock} attach")
        term2.run("echo hi")

        # When the first terminal becomes active again, the server link should
        # end up pointing back at it once the hook has a moment to run.
        term1.run("echo hi")
        delay()

        assert resolve_symlink(auth_sock) == term1.login_auth_sock
        assert resolve_symlink(auth_sock) != term2.login_auth_sock


class TestCommands:
    def test_show_server_link_unset(self, term: Term, socklink: Path):
        output = term.run(f"{socklink} show-server-link", stdout=True)
        assert output == ""

    def test_set_tty_link(self, sandbox: Sandbox, term: Term, socklink: Path):
        term.run(f"{socklink} set-tty-link")
        ttys_dir = sandbox.root / "tmp" / "socklink" / "ttys"
        tty_socks = os.listdir(ttys_dir)
        assert len(tty_socks) == 1
        assert resolve_symlink(ttys_dir / tty_socks[0]) == term.login_auth_sock


class TestInstallation:
    def test_set_section_no_file(self, sandbox: Sandbox, stub: SocklinkStub):
        rc_file = sandbox.root / "test_rc_file"
        stub.run(
            "set-socklink-section",
            rc_file,
            stdin=dedent("""\
        foo
        bar
        """),
        )

        assert rc_file.read_text() == dedent("""\
        ### SOCKLINK INSTALLATION BEGIN
        foo
        bar
        ### SOCKLINK INSTALLATION END
        """)

    def test_set_section_empty_file(self, sandbox: Sandbox, stub: SocklinkStub):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.touch()
        stub.run(
            "set-socklink-section",
            rc_file,
            stdin=dedent("""\
        foo
        bar
        """),
        )

        assert rc_file.read_text() == dedent("""\
        ### SOCKLINK INSTALLATION BEGIN
        foo
        bar
        ### SOCKLINK INSTALLATION END
        """)

    def test_set_section_single_char_file(self, sandbox: Sandbox, stub: SocklinkStub):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.write_text("a")
        stub.run(
            "set-socklink-section",
            rc_file,
            stdin=dedent("""\
        foo
        bar
        """),
        )

        assert rc_file.read_text() == dedent("""\
        a

        ### SOCKLINK INSTALLATION BEGIN
        foo
        bar
        ### SOCKLINK INSTALLATION END
        """)

    def test_set_section_single_char_file_with_lf(
        self, sandbox: Sandbox, stub: SocklinkStub
    ):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.write_text("a\n")
        stub.run(
            "set-socklink-section",
            rc_file,
            stdin=dedent("""\
        foo
        bar
        """),
        )

        assert rc_file.read_text() == dedent("""\
        a

        ### SOCKLINK INSTALLATION BEGIN
        foo
        bar
        ### SOCKLINK INSTALLATION END
        """)

    def test_set_section_empty_section(self, sandbox: Sandbox, stub: SocklinkStub):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.write_text(
            dedent("""\
        ### SOCKLINK INSTALLATION BEGIN
        ### SOCKLINK INSTALLATION END
        """)
        )
        stub.run(
            "set-socklink-section",
            rc_file,
            stdin=dedent("""\
        foo
        bar
        """),
        )

        assert rc_file.read_text() == dedent("""\
        ### SOCKLINK INSTALLATION BEGIN
        foo
        bar
        ### SOCKLINK INSTALLATION END
        """)

    def test_set_section_not_preeixsting(self, sandbox: Sandbox, stub: SocklinkStub):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.write_text(
            dedent("""\
            This is a test
            The remainder of this file should be unmodified.
            """)
        )
        stub.run(
            "set-socklink-section",
            rc_file,
            stdin=dedent("""\
            foo
            bar
            """),
        )

        assert rc_file.read_text() == dedent("""\
            This is a test
            The remainder of this file should be unmodified.

            ### SOCKLINK INSTALLATION BEGIN
            foo
            bar
            ### SOCKLINK INSTALLATION END
            """)

    def test_set_section_not_preeixsting_no_lf(
        self, sandbox: Sandbox, stub: SocklinkStub
    ):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.write_text(
            dedent("""\
            This is a test
            The remainder of this file should be unmodified.""")
        )
        stub.run(
            "set-socklink-section",
            rc_file,
            stdin=dedent("""\
            foo
            bar
            """),
        )

        assert rc_file.read_text() == dedent("""\
            This is a test
            The remainder of this file should be unmodified.

            ### SOCKLINK INSTALLATION BEGIN
            foo
            bar
            ### SOCKLINK INSTALLATION END
            """)

    def test_set_section_preserves_rest(self, sandbox: Sandbox, stub: SocklinkStub):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.write_text(
            dedent("""\
            This is a test

            ### SOCKLINK INSTALLATION BEGIN
            ### SOCKLINK INSTALLATION END
            The remainder of this file should be unmodified.
            """)
        )
        stub.run(
            "set-socklink-section",
            rc_file,
            stdin=dedent("""\
            foo
            bar
            """),
        )

        assert rc_file.read_text() == dedent("""\
            This is a test

            ### SOCKLINK INSTALLATION BEGIN
            foo
            bar
            ### SOCKLINK INSTALLATION END
            The remainder of this file should be unmodified.
            """)

    def test_has_manual_config_head(self, sandbox: Sandbox, stub: SocklinkStub):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.write_text(
            dedent("""\
            socklink.sh set-tty-link
            ### SOCKLINK INSTALLATION BEGIN
            echo foo
            ### SOCKLINK INSTALLATION END
            echo bar
            """)
        )
        assert stub.run_test("has-manual-config", rc_file)

    def test_has_manual_config_installation(self, sandbox: Sandbox, stub: SocklinkStub):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.write_text(
            dedent("""\
            echo foo
            ### SOCKLINK INSTALLATION BEGIN
            socklink.sh set-tty-link
            ### SOCKLINK INSTALLATION END
            echo bar
            """)
        )
        assert not stub.run_test("has-manual-config", rc_file)

    def test_has_manual_config_tail(self, sandbox: Sandbox, stub: SocklinkStub):
        rc_file = sandbox.root / "test_rc_file"
        rc_file.write_text(
            dedent("""\
            echo foo
            ### SOCKLINK INSTALLATION BEGIN
            echo bar
            ### SOCKLINK INSTALLATION END
            socklink.sh show-server-link
            """)
        )
        assert stub.run_test("has-manual-config", rc_file)
