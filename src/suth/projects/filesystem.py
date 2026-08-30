import json
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


def resolve_under_root(registry: ProjectRegistry, rel_path: str) -> Path:
    """Resolve a browse/config path.

    Relative paths (including `.` and `./…`) are rooted at the registry's
    project directory. Absolute paths and `~` are allowed so the GUI can
    point a config at another local app.
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
    return candidate.resolve()


def config_file_in_dir(directory: Path) -> Path:
    return directory / CONFIG_FILENAME


def resolve_registered_config_path(registry: ProjectRegistry, project_id: str) -> Path:
    stored = registry.config_path(project_id)
    return resolve_under_root(registry, stored)


def browse(registry: ProjectRegistry, rel_path: str = ".") -> dict:
    current = resolve_under_root(registry, rel_path)
    if not current.is_dir():
        raise ValueError(f"not a directory: {rel_path}")

    root = project_root(registry)
    parent_path = current.parent
    parent = None if parent_path == current else format_path(root, parent_path)

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
