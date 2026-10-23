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
        self._mtime: float | None = None
        self._reload_if_changed()

    def _reload_if_changed(self) -> None:
        # The API, MCP server and CLI are separate processes sharing this file;
        # re-read on change so a project registered in one shows up in the others.
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            self._entries, self._mtime = {}, None
            return
        if mtime != self._mtime:
            self._entries = json.loads(self.path.read_text())
            self._mtime = mtime

    def list_project_ids(self) -> list[str]:
        self._reload_if_changed()
        return sorted(self._entries)

    def resolved_config_path(self, project_id: str) -> Path:
        """The registered config path as an absolute Path. Stored entries are
        relative to the registry file's directory, not the process's cwd."""
        stored = Path(self.config_path(project_id)).expanduser()
        if stored.is_absolute():
            return stored.resolve()
        return (self.path.resolve().parent / stored).resolve()

    def config_path(self, project_id: str) -> str:
        self._reload_if_changed()
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
        self._reload_if_changed()
        self._entries[project_id] = stored
        self._write()

    def unregister(self, project_id: str) -> None:
        """Remove a project from the allowlist and persist to disk."""
        self._reload_if_changed()
        if project_id not in self._entries:
            raise UnregisteredProjectError(
                f"project_id '{project_id}' is not registered in {self.path}"
            )
        del self._entries[project_id]
        self._write()

    def _write(self) -> None:
        self.path.write_text(json.dumps(self._entries, indent=2) + "\n")
        self._mtime = self.path.stat().st_mtime
