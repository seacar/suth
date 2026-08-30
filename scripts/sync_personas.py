#!/usr/bin/env python3
"""Sync personas/library/*.yaml into Postgres — plan Phase 2 DB-as-cache.

The YAML files are the source of truth in git. If a persona's content changed
since its latest stored version, this inserts a NEW version row rather than
overwriting it, so a past session's `persona_version` still points at the
definition it actually ran against.

Run via: specific exec cli -- .venv/bin/python scripts/sync_personas.py
"""

from suth.db import get_engine
from suth.personas.loader import LIBRARY_DIR, load_persona_file
from suth.personas.repository import save_persona


def main() -> None:
    engine = get_engine()
    for path in sorted(LIBRARY_DIR.glob("*.yaml")):
        persona = load_persona_file(path)
        version, changed = save_persona(engine, persona)
        if changed:
            print(f"synced: {persona.id} -> v{version}")
        else:
            print(f"unchanged: {persona.id} (v{version})")


if __name__ == "__main__":
    main()
