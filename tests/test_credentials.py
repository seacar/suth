import json

import pytest

from suth.credentials import (
    credential_env_var,
    credential_is_configured,
    credential_ref,
    credentials_store_path,
    get_credential_value,
    load_credentials,
    resolve_credential,
    save_credentials,
)


def test_credential_env_var_for_known_and_custom_providers():
    assert credential_env_var("ollama") is None
    assert credential_env_var("anthropic") == "ANTHROPIC_API_KEY"
    assert credential_env_var("openai") == "OPENAI_API_KEY"
    assert credential_env_var("groq") == "SUTH_GROQ_API_KEY"


def test_credential_ref_uses_env_prefix():
    assert credential_ref("anthropic") == "env:ANTHROPIC_API_KEY"
    assert credential_ref("ollama") is None


def test_save_and_resolve_credentials_from_local_store(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    save_credentials({"ANTHROPIC_API_KEY": "sk-test"}, tmp_path)

    store = credentials_store_path(tmp_path)
    assert store.is_file()
    assert json.loads(store.read_text())["ANTHROPIC_API_KEY"] == "sk-test"
    assert store.stat().st_mode & 0o777 == 0o600

    assert get_credential_value("ANTHROPIC_API_KEY", tmp_path) == "sk-test"
    assert resolve_credential("env:ANTHROPIC_API_KEY", tmp_path) == "sk-test"
    assert credential_is_configured("env:ANTHROPIC_API_KEY", tmp_path) is True


def test_resolve_credentials_prefers_process_env(tmp_path, monkeypatch):
    save_credentials({"OPENAI_API_KEY": "stored-key"}, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")

    assert resolve_credential("env:OPENAI_API_KEY", tmp_path) == "env-key"


def test_resolve_credentials_missing_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    load_credentials(tmp_path)

    with pytest.raises(RuntimeError, match="missing credential"):
        resolve_credential("env:ANTHROPIC_API_KEY", tmp_path)
