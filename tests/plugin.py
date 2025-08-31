from pathlib import Path
import subprocess
from typing import Generator, Protocol

import pytest

from tests.testlib import (
    Sandbox,
    Term,
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


class TermNameProvider:
    """Generates a unique per-test name for a terminal"""

    n: int

    def __init__(self):
        self.n = 1

    def make_name(self) -> str:
        name = f"term{self.n}"
        self.n += 1
        return name


@pytest.fixture
def term_name_provider() -> TermNameProvider:
    return TermNameProvider()


@pytest.fixture
def term(
    sandbox: Sandbox, term_name_provider: TermNameProvider
) -> Generator[Term, None, None]:
    with Term(term_name_provider.make_name(), sandbox) as t:
        yield t


class MakeTerm(Protocol):
    def __call__(self, **kwargs) -> Term: ...


@pytest.fixture
def make_term(
    request: pytest.FixtureRequest,
    sandbox: Sandbox,
    term_name_provider: TermNameProvider,
) -> MakeTerm:
    def fn(login_sock: bool = True):
        term = Term(
            term_name_provider.make_name(),
            sandbox,
            login_sock=login_sock,
        )
        request.addfinalizer(lambda: term.close())
        return term

    return fn


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
