"""API key handling in the master agent."""

import os

import pytest

from app import resolve_api_key
from app_agents.master_agent import MasterAgent


def test_the_key_is_not_written_to_the_shared_environment(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    MasterAgent(api_key="visitor-key")
    assert "OPENAI_API_KEY" not in os.environ


def test_each_agent_keeps_its_own_key():
    a = MasterAgent(api_key="key-a")
    b = MasterAgent(api_key="key-b")
    assert a.model._client.api_key == "key-a"
    assert b.model._client.api_key == "key-b"


def test_a_missing_key_is_rejected():
    with pytest.raises(ValueError):
        MasterAgent(api_key="")


# --- which key a request uses (public Space vs local) ---


def test_the_visitor_key_always_wins():
    assert resolve_api_key("  sk-visitor ", "sk-env", on_space=True) == "sk-visitor"
    assert resolve_api_key("sk-visitor", "sk-env", on_space=False) == "sk-visitor"


def test_locally_the_environment_key_is_the_fallback():
    assert resolve_api_key("", "sk-env", on_space=False) == "sk-env"
    assert resolve_api_key(None, None, on_space=False) is None


def test_on_a_public_space_the_owners_key_is_never_used():
    assert resolve_api_key("", "sk-owner-secret", on_space=True) is None
    assert resolve_api_key(None, "sk-owner-secret", on_space=True) is None
