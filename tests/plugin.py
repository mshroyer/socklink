from pathlib import Path
from typing import Generator

import pytest

from tests.testlib import Sandbox, SocketManager, Terminal


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Sandbox:
    return Sandbox(tmp_path, monkeypatch)


@pytest.fixture
def socket_manager(sandbox) -> Generator[SocketManager, None, None]:
    with SocketManager(sandbox) as m:
        yield m


@pytest.fixture
def terminal(sandbox) -> Generator[Terminal, None, None]:
    with Terminal(sandbox) as t:
        yield t
