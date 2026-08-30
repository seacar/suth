import json
import os
import re
from pathlib import Path

DEFAULT_STORE_DIR = ".suth"
DEFAULT_STORE_FILENAME = "credentials.json"

REMOTE_PROVIDER_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def credential_env_var(provider: str) -> str | None:
    """Return the env var name used to store a provider's API key, if any."""
    if provider == "ollama":
        return None
    if provider in REMOTE_PROVIDER_ENV_VARS:
        return REMOTE_PROVIDER_ENV_VARS[provider]
    normalized = re.sub(r"[^a-z0-9]+", "_", provider.lower()).strip("_")
    if not normalized:
        return None
    return f"SUTH_{normalized.upper()}_API_KEY"


def credential_ref(provider: str) -> str | None:
    env_var = credential_env_var(provider)
    return f"env:{env_var}" if env_var else None


def parse_credential_ref(ref: str) -> str:
    if not ref.startswith("env:"):
        raise ValueError(f"unsupported credential reference '{ref}' (expected 'env:VAR_NAME')")
    return ref.removeprefix("env:")


def credentials_store_path(root: Path | None = None) -> Path:
    base = root or Path.cwd()
    override = os.environ.get("SUTH_CREDENTIALS_PATH")
    if override:
        return Path(override).expanduser()
    return base / DEFAULT_STORE_DIR / DEFAULT_STORE_FILENAME


def load_credentials(root: Path | None = None) -> dict[str, str]:
    path = credentials_store_path(root)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items() if value}


def save_credentials(values: dict[str, str], root: Path | None = None) -> None:
    path = credentials_store_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_credentials(root)
    existing.update({key: value for key, value in values.items() if value})
    path.write_text(json.dumps(existing, indent=2) + "\n")
    path.chmod(0o600)


def get_credential_value(env_var: str, root: Path | None = None) -> str | None:
    value = os.environ.get(env_var)
    if value:
        return value
    return load_credentials(root).get(env_var)


def credential_is_configured(ref: str, root: Path | None = None) -> bool:
    try:
        env_var = parse_credential_ref(ref)
    except ValueError:
        return False
    return bool(get_credential_value(env_var, root))


def resolve_credential(ref: str, root: Path | None = None) -> str:
    """Resolve a credential reference like `env:ANTHROPIC_API_KEY`.

    Checks process env first, then the local `.suth/credentials.json` store.
    """
    env_var = parse_credential_ref(ref)
    value = get_credential_value(env_var, root)
    if not value:
        raise RuntimeError(
            f"missing credential for provider: env var '{env_var}' is not set "
            "and no value was found in the local credentials store"
        )
    return value
