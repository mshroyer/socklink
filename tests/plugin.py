from pathlib import Path

import pytest

from tests.testlib import Sandbox, Terminal


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Sandbox:
    return Sandbox(tmp_path, monkeypatch)


@pytest.fixture
def terminal(sandbox) -> Terminal:
    return Terminal(sandbox)
