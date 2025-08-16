from pathlib import Path
from typing import Generator

import pytest

from tests.testlib import Sandbox, Terminal, TsockStub, get_project_dir


@pytest.fixture(scope="session")
def tsock() -> Path:
    return get_project_dir() / "tsock.sh"


@pytest.fixture(scope="session")
def stub(tsock) -> TsockStub:
    return TsockStub(tsock)


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
