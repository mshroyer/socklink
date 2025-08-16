from pathlib import Path
import subprocess
from typing import Generator

import pytest

from tests.testlib import (
    Sandbox,
    Terminal,
    TsockStub,
    fail_with_subprocess_error,
    get_project_dir,
)


@pytest.fixture(scope="session")
def tsock() -> Path:
    return get_project_dir() / "tsock.sh"


@pytest.fixture
def sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Sandbox, None, None]:
    with Sandbox(tmp_path, monkeypatch) as s:
        yield s


@pytest.fixture
def terminal(sandbox) -> Generator[Terminal, None, None]:
    with Terminal(sandbox) as t:
        yield t


@pytest.fixture
def stub(tsock: Path, sandbox: Sandbox) -> TsockStub:
    return TsockStub(tsock, sandbox)


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
