import json
import os
from pathlib import Path

from suth.mcp_server.registry import ProjectRegistry

CONFIG_FILENAME = "suth_config.json"
SKIP_DIR_NAMES = {
    ".git",
    ".next",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


def project_root(registry: ProjectRegistry) -> Path:
    return registry.path.resolve().parent


def format_path(root: Path, path: Path) -> str:
    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        return str(path.resolve())
    if rel.as_posix() == ".":
        return "."
    return f"./{rel.as_posix()}"


def relative_path(root: Path, path: Path) -> str:
    return format_path(root, path)


class PathNotAllowedError(Exception):
    """A browse/config path resolved outside every allowed root."""


def allowed_roots(registry: ProjectRegistry) -> list[Path]:
    """Directories the project browser may read and write under: the
    registry's own directory, plus SUTH_BROWSE_ROOTS (os.pathsep-separated),
    which defaults to the user's home directory."""
    raw = os.environ.get("SUTH_BROWSE_ROOTS")
    extra = [p for p in raw.split(os.pathsep) if p.strip()] if raw else [str(Path.home())]
    return [project_root(registry), *(Path(p).expanduser().resolve() for p in extra)]


def is_allowed(registry: ProjectRegistry, path: Path) -> bool:
    return any(path == root or path.is_relative_to(root) for root in allowed_roots(registry))


def resolve_under_root(registry: ProjectRegistry, rel_path: str) -> Path:
    """Resolve a browse/config path.

    Relative paths (including `.` and `./…`) are rooted at the registry's
    project directory. Absolute paths and `~` are allowed so the GUI can
    point a config at another local app — but only inside allowed_roots(),
    since these paths come from API callers and are listed, read and written.
    """
    root = project_root(registry)
    clean = (rel_path or ".").strip()
    if clean.startswith("~"):
        candidate = Path(clean).expanduser()
    elif Path(clean).is_absolute():
        candidate = Path(clean)
    else:
        if clean.startswith("./"):
            clean = clean[2:]
        if clean in ("", "."):
            return root
        candidate = root / clean
    resolved = candidate.resolve()  # resolves `..` and symlinks before the check
    if not is_allowed(registry, resolved):
        raise PathNotAllowedError(
            f"{rel_path!r} is outside the allowed directories; set SUTH_BROWSE_ROOTS to widen them"
        )
    return resolved


def config_file_in_dir(directory: Path) -> Path:
    return directory / CONFIG_FILENAME


def resolve_registered_config_path(registry: ProjectRegistry, project_id: str) -> Path:
    return registry.resolved_config_path(project_id)


def browse(registry: ProjectRegistry, rel_path: str = ".") -> dict:
    current = resolve_under_root(registry, rel_path)
    if not current.is_dir():
        raise ValueError(f"not a directory: {rel_path}")

    root = project_root(registry)
    parent_path = current.parent
    parent = (
        None
        if parent_path == current or not is_allowed(registry, parent_path)
        else format_path(root, parent_path)
    )

    entries = []
    try:
        children = sorted(current.iterdir(), key=lambda p: p.name.lower())
    except OSError as e:
        raise ValueError(f"cannot read directory {current}: {e}") from e

    for child in children:
        try:
            is_dir = child.is_dir()
        except OSError:
            continue
        if not is_dir:
            continue
        if child.name.startswith("."):
            continue
        if child.name in SKIP_DIR_NAMES:
            continue
        entries.append(
            {
                "name": child.name,
                "path": format_path(root, child),
                "kind": "dir",
            }
        )

    return {
        "path": format_path(root, current),
        "abs_path": str(current),
        "parent": parent,
        "entries": entries,
        "config_exists": config_file_in_dir(current).is_file(),
    }


def config_at(registry: ProjectRegistry, rel_dir: str) -> dict:
    directory = resolve_under_root(registry, rel_dir)
    if not directory.is_dir():
        raise ValueError(f"not a directory: {rel_dir}")

    root = project_root(registry)
    config_path = config_file_in_dir(directory)
    exists = config_path.is_file()
    config = json.loads(config_path.read_text()) if exists else None

    return {
        "config_dir": format_path(root, directory),
        "config_path": format_path(root, config_path),
        "exists": exists,
        "config": config,
    }
