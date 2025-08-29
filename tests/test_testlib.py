import pytest

from tests.testlib import (
    Term,
    TermCommandError,
)


def test_term_error(term: Term):
    with pytest.raises(TermCommandError):
        term.run("false")
