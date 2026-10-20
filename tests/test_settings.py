import pytest
from pydantic import ValidationError

from finfacts.settings import Settings


def test_rejects_user_agent_without_contact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "FinFacts")
    with pytest.raises(ValidationError, match="SEC_USER_AGENT"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_rejects_rate_above_sec_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "FinFacts/0.1 a@example.com")
    monkeypatch.setenv("SEC_MAX_RPS", "11")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
