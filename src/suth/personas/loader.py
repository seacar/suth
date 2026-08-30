from pathlib import Path

import yaml

from suth.personas.schema import Persona

LIBRARY_DIR = Path(__file__).parent / "library"


def load_persona_file(path: str | Path) -> Persona:
    raw = yaml.safe_load(Path(path).read_text())
    return Persona.model_validate(raw)


def load_persona(persona_id: str) -> Persona:
    """Load a persona by id from the built-in library fixtures."""
    path = LIBRARY_DIR / f"{persona_id}.yaml"
    if not path.exists():
        available = sorted(p.stem for p in LIBRARY_DIR.glob("*.yaml"))
        raise FileNotFoundError(
            f"No persona '{persona_id}' in library. Available: {available}"
        )
    return load_persona_file(path)
