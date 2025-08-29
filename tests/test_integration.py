import os
from pathlib import Path
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
    monkeypatch.setenv("TEST_SHELL", shell)


def delay():
    """Wait some amount of time in hopes tmux hooks have settled"""

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


def test_unset(make_term: MakeTerm):
    term = make_term(login_sock=False)
    assert term.get_auth_sock() is None


def test_set(term: Term):
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
