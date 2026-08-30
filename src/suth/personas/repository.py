from sqlalchemy import Engine, MetaData, insert, select

from suth.personas.schema import Persona


def load_persona_from_db(engine: Engine, persona_id: str) -> Persona:
    """DB-as-cache read path (plan Phase 2): the YAML files under
    personas/library/ are the source of truth in git; `scripts/sync_personas.py`
    upserts them into Postgres, and the running harness reads from there so
    Postgres — not the filesystem — is what a session actually ran against.
    """
    metadata = MetaData()
    metadata.reflect(bind=engine, only=["personas"])
    t = metadata.tables["personas"]
    with engine.connect() as conn:
        row = conn.execute(
            select(t.c.definition_jsonb, t.c.version)
            .where(t.c.id == persona_id)
            .order_by(t.c.version.desc())
            .limit(1)
        ).first()
    if row is None:
        raise FileNotFoundError(
            f"persona '{persona_id}' not found in Postgres — run "
            "`specific exec cli -- .venv/bin/python scripts/sync_personas.py` first"
        )
    definition, version = row
    persona = Persona.model_validate(definition)
    persona.version = version
    return persona


def save_persona(engine: Engine, persona: Persona) -> tuple[int, bool]:
    """Insert `persona` as a new version if its content differs from the
    latest stored version (or if it has never been stored); no-op otherwise.
    Returns (version now on record, whether a new row was inserted). Shared
    by scripts/sync_personas.py and the MCP `create_persona` tool so there's
    one versioning policy, not two.
    """
    metadata = MetaData()
    metadata.reflect(bind=engine, only=["personas"])
    t = metadata.tables["personas"]
    definition = persona.model_dump(mode="json", exclude={"version"})

    with engine.begin() as conn:
        latest = conn.execute(
            select(t.c.version, t.c.definition_jsonb)
            .where(t.c.id == persona.id)
            .order_by(t.c.version.desc())
            .limit(1)
        ).first()

        if latest and latest.definition_jsonb == definition:
            return latest.version, False

        next_version = (latest.version + 1) if latest else 1
        conn.execute(
            insert(t).values(
                id=persona.id,
                project_id=None,
                name=persona.name or persona.id,
                version=next_version,
                definition_jsonb=definition,
            )
        )
        return next_version, True


def list_personas(engine: Engine) -> list[dict]:
    """Latest version of every persona in Postgres."""
    metadata = MetaData()
    metadata.reflect(bind=engine, only=["personas"])
    t = metadata.tables["personas"]
    with engine.connect() as conn:
        rows = conn.execute(select(t)).mappings().all()
    latest: dict[str, dict] = {}
    for row in rows:
        current = latest.get(row["id"])
        if current is None or row["version"] > current["version"]:
            latest[row["id"]] = dict(row)
    return sorted(latest.values(), key=lambda r: r["id"])
