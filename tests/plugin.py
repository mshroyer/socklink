from pathlib import Path
import subprocess
from typing import Generator, Protocol

import pytest

from tests.testlib import (
    Sandbox,
    Terminal,
    SocklinkStub,
    fail_with_subprocess_error,
    get_project_dir,
)


@pytest.fixture(scope="session")
def socklink() -> Path:
    return get_project_dir() / "socklink.sh"


@pytest.fixture
def sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Sandbox, None, None]:
    with Sandbox(tmp_path, monkeypatch) as s:
        yield s


@pytest.fixture
def tmux_sock(sandbox: Sandbox) -> Path:
    return sandbox.reserve_tmux_socket()


class DebugFilenameProvider:
    n: int

    def __init__(self):
        self.n = 1

    def make_filename(self) -> str:
        name = f"terminal{self.n}-debug.txt"
        self.n += 1
        return name


@pytest.fixture
def debug_filename_provider() -> DebugFilenameProvider:
    return DebugFilenameProvider()


@pytest.fixture
def terminal(
    sandbox: Sandbox, debug_filename_provider: DebugFilenameProvider
) -> Generator[Terminal, None, None]:
    with Terminal(sandbox, debug_filename=debug_filename_provider.make_filename()) as t:
        yield t


class MakeTerminal(Protocol):
    def __call__(self, **kwargs) -> Terminal: ...


@pytest.fixture
def make_terminal(
    sandbox, debug_filename_provider: DebugFilenameProvider
) -> MakeTerminal:
    def make_terminal(login_sock: bool = True):
        return Terminal(
            sandbox,
            login_sock=login_sock,
            debug_filename=debug_filename_provider.make_filename(),
        )

    return make_terminal


@pytest.fixture
def stub(socklink: Path, sandbox: Sandbox) -> SocklinkStub:
    return SocklinkStub(socklink, sandbox)


# Wrap test case invocations to clarify subprocess errors
#
# Wraps each test function so that we can capture any uncaught
# CalledProcessErrors and instead fail the test, printing the subprocess's
# stdout and stderr without an excessive and unhelpful Python stack trace.
#
# Ideally, we could just implement pytest_runtest_call instead, but as of pytest
# 8.3.5 doing this without `wraptest` this results in duplicate invocations of
# the test method--and with it, an generator we can't use to intercept the
# exception.
#
# Cloned from https://github.com/mshroyer/coursepointer/


@pytest.hookimpl
def pytest_itemcollected(item):
    item.runtest_wrapped = item.runtest
    item.runtest = _runtest.__get__(item, item.__class__)


def _runtest(self):
    try:
        self.runtest_wrapped()
    except subprocess.CalledProcessError as e:
        fail_with_subprocess_error(e)
