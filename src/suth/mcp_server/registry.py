import json
import os
from pathlib import Path

DEFAULT_REGISTRY_PATH = "mcp_projects.json"


class UnregisteredProjectError(Exception):
    """Raised when a caller references a project_id not in the allowlist."""


class ProjectRegistry:
    """Server-side allowlist of project_id -> suth_config.json path.

    This is the safety boundary from plan Phase 4: an MCP caller supplies a
    `project_id` string, never a URL or config path — the actual `base_url` a
    session drives against always comes from a config file the *operator* of
    this MCP server pre-registered, so a caller can't inject an arbitrary
    target by passing a crafted project_id or config path.
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.environ.get("SUTH_MCP_PROJECTS", DEFAULT_REGISTRY_PATH))
        self._entries: dict[str, str] = {}
        if self.path.exists():
            self._entries = json.loads(self.path.read_text())

    def list_project_ids(self) -> list[str]:
        return sorted(self._entries)

    def config_path(self, project_id: str) -> str:
        if project_id not in self._entries:
            raise UnregisteredProjectError(
                f"project_id '{project_id}' is not registered in {self.path} — "
                f"registered projects: {self.list_project_ids()}"
            )
        return self._entries[project_id]

    def register(self, project_id: str, config_path: str | Path) -> None:
        """Add a project to the allowlist and persist to disk."""
        resolved = Path(config_path).expanduser().resolve()
        if not resolved.is_file():
            raise ValueError(f"config file does not exist: {resolved}")

        root = self.path.resolve().parent
        try:
            rel = resolved.relative_to(root)
            stored = "." if rel.as_posix() == "." else f"./{rel.as_posix()}"
        except ValueError:
            stored = str(resolved)
        self._entries[project_id] = stored
        self.path.write_text(json.dumps(self._entries, indent=2) + "\n")

    def unregister(self, project_id: str) -> None:
        """Remove a project from the allowlist and persist to disk."""
        if project_id not in self._entries:
            raise UnregisteredProjectError(
                f"project_id '{project_id}' is not registered in {self.path}"
            )
        del self._entries[project_id]
        self.path.write_text(json.dumps(self._entries, indent=2) + "\n")
