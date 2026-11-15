"""API key handling in the master agent."""

import os

import pytest

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
