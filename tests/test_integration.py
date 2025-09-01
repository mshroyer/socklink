import os
from pathlib import Path
import platform
import shutil
from time import sleep

import pytest

from tests.plugin import MakeTerm
from tests.testlib import (
    Sandbox,
    Term,
    SocklinkStub,
    resolve_symlink,
)


@pytest.fixture(
    params=[
        pytest.param(
            "bash",
            marks=pytest.mark.skipif(
                shutil.which("bash") is None, reason="bash not found"
            ),
        ),
        pytest.param(
            "zsh",
            marks=pytest.mark.skipif(
                shutil.which("zsh") is None, reason="zsh not found"
            ),
        ),
    ],
    ids=lambda s: s,
)
def shell(request):
    return request.param


@pytest.fixture(autouse=True)
def _expose_shell(monkeypatch, shell):
    if shell == "zsh":
        # Fixes GitHub Actions on Ubuntu 24.04
        shell = "zsh --no-globalrcs"
    monkeypatch.setenv("TEST_SHELL", shell)


def delay():
    """Wait some amount of time in hopes tmux hooks have settled"""

    if platform.system() == "Darwin":
        # macOS is flakier than the others when it comes to reading the
        # updated target of the server symlink
        sleep(0.5)
    else:
        sleep(0.25)


def test_show_server_link_unset(term: Term, socklink: Path):
    output = term.run(f"{socklink} show-server-link", stdout=True)
    assert output == ""


def test_set_tty_link(sandbox: Sandbox, term: Term, socklink: Path):
    term.run(f"{socklink} set-tty-link")
    ttys_dir = sandbox.root / "tmp" / "socklink" / "ttys"
    tty_socks = os.listdir(ttys_dir)
    assert len(tty_socks) == 1
    assert resolve_symlink(ttys_dir / tty_socks[0]) == term.login_auth_sock


def test_login_sock_unset(make_term: MakeTerm):
    term = make_term(login_sock=False)
    assert term.get_auth_sock() is None


def test_login_sock_set(term: Term):
    assert term.get_auth_sock() is not None


def test_tmux_session(sandbox: Sandbox, term: Term):
    socket = sandbox.reserve_tmux_socket()
    term.run(f"tmux -S {socket}")
    assert term.get_auth_sock() is not None


def test_default_setup(tmux_sock: Path, make_term: MakeTerm, stub: SocklinkStub):
    stub.run("setup")

    # When testing setup, we have to explicilty make the terminal after
    # running setup so that its newly-setup login shell hooks run.
    term = make_term()
    term.run(f"tmux -S {tmux_sock}")

    auth_sock = term.get_auth_sock()
    assert resolve_symlink(auth_sock) == term.login_auth_sock


def test_second_concurrent_client(
    tmux_sock: Path, make_term: MakeTerm, stub: SocklinkStub
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
    tmux_sock: Path, make_term: MakeTerm, stub: SocklinkStub
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
    tmux_sock: Path, make_term: MakeTerm, stub: SocklinkStub
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


def test_client_without_login_sock(
    tmux_sock: Path, make_term: MakeTerm, stub: SocklinkStub
):
    stub.run("setup")

    term1 = make_term(login_sock=True)
    term1.run(f"tmux -S {tmux_sock}")
    auth_sock = term1.get_auth_sock()

    # Connecting the second client without an SSH_AUTH_SOCK of its own
    # should overwrite the login socket mapped for the first client.  This
    # way, for example, if client 1 has a hardware token with
    # proof-of-presence, SSH won't try to use that when the user is
    # sitting at client 2, and may fall back to other authentication
    # methods if possible.
    term2 = make_term(login_sock=False)
    term2.run(f"tmux -S {tmux_sock} attach")
    delay()
    assert resolve_symlink(auth_sock) is None


def test_multiple_sessions(tmux_sock: Path, make_term: MakeTerm, stub: SocklinkStub):
    stub.run("setup")

    term1 = make_term(login_sock=True)
    term1.run(f"tmux -S {tmux_sock} new-session -s sess1")
    auth_sock1 = term1.get_auth_sock()

    term2 = make_term(login_sock=True)
    term2.run(f"tmux -S {tmux_sock} new-session -s sess2")
    auth_sock2 = term2.get_auth_sock()

    # Shells running in the two sessions should share the same
    # server-keyed authentication socket.
    assert auth_sock1 == auth_sock2


def test_gc_tty_links(sandbox: Sandbox, make_term: MakeTerm, stub: SocklinkStub):
    stub.run("setup")
    ttys = sandbox.root / "tmp" / "socklink" / "ttys"

    with make_term(login_sock=True):
        assert len(list(ttys.glob("*"))) == 1

    # Opening a second term after the first has closed should GC the original
    # link when set-tty-link runs, if the same pty name isn't reused; either
    # way we're still at one link in the directory.
    with make_term(login_sock=True):
        assert len(list(ttys.glob("*"))) == 1

        # Opening a third term while the second should leave the existing link
        # in place, on the other hand.
        with make_term(login_sock=True):
            assert len(list(ttys.glob("*"))) == 2

            with make_term(login_sock=True):
                assert len(list(ttys.glob("*"))) == 3

                with make_term(login_sock=True):
                    assert len(list(ttys.glob("*"))) == 4

    # We aren't reusing all of the above ptys at this point, so here we will
    # have needed to GC at least three of them (or four, if the current isn't
    # reused) for the test to succeed.  In particular, this makes sure we
    # aren't failing to enumerate and GC links to now-nonexistent auth
    # sockets.
    with make_term(login_sock=True):
        assert len(list(ttys.glob("*"))) == 1
