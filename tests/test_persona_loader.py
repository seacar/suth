import pytest
from pydantic import ValidationError

from suth.personas.loader import LIBRARY_DIR, load_persona, load_persona_file
from suth.personas.schema import Persona

STARTER_LIBRARY = [
    "impatient-mobile-shopper-v2",
    "elderly-low-vision-v1",
    "screen-reader-only-v1",
    "non-native-speaker-v1",
    "power-user-v1",
]


def test_loads_builtin_impatient_mobile_shopper():
    persona = load_persona("impatient-mobile-shopper-v2")
    assert persona.id == "impatient-mobile-shopper-v2"
    assert persona.digital_literacy == "low"
    assert persona.device == "mobile"
    assert len(persona.forbidden_assumptions) >= 1
    assert persona.rule("frustration_score_exceeds") is not None


def test_unknown_persona_raises_with_available_list():
    with pytest.raises(FileNotFoundError, match="impatient-mobile-shopper-v2"):
        load_persona("does-not-exist")


def test_render_objective_substitutes_template():
    persona = load_persona("impatient-mobile-shopper-v2")
    assert persona.render_objective("find cheap house") == "find cheap house"


def test_rejects_missing_required_field(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("digital_literacy: low\ndevice: mobile\n")  # missing id
    with pytest.raises(ValidationError):
        load_persona_file(bad)


def test_rejects_invalid_digital_literacy(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: x\ndigital_literacy: expert\ndevice: mobile\n")
    with pytest.raises(ValidationError):
        load_persona_file(bad)


def test_rejects_invalid_abandonment_trigger(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "id: x\ndigital_literacy: low\ndevice: mobile\n"
        "abandonment_rules:\n  - trigger: made_up_trigger\n    threshold: 1\n"
    )
    with pytest.raises(ValidationError):
        load_persona_file(bad)


@pytest.mark.parametrize("persona_id", STARTER_LIBRARY)
def test_starter_library_all_load(persona_id):
    persona = load_persona(persona_id)
    assert persona.id == persona_id
    assert persona.name


def test_starter_library_has_no_extra_files():
    on_disk = {p.stem for p in LIBRARY_DIR.glob("*.yaml")}
    assert on_disk == set(STARTER_LIBRARY)


def test_screen_reader_persona_is_keyboard_only():
    persona = load_persona("screen-reader-only-v1")
    assert persona.interaction_mode == "keyboard"


def test_default_interaction_mode_is_pointer():
    persona = load_persona("power-user-v1")
    assert persona.interaction_mode == "pointer"
