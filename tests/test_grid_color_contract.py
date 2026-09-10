"""Grid colors must be rejected at submission before canonical execution."""

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from wellplot.agent.graph.worker_contracts import construction_model
from wellplot.model.intent import AuthoringGridIntent


@pytest.mark.parametrize(
    "field",
    [
        "horizontal_major_color",
        "horizontal_minor_color",
        "vertical_main_color",
        "vertical_secondary_color",
    ],
)
@pytest.mark.parametrize("reconstruct", [True, False])
def test_grid_colors_match_canonical_nonempty_constraint(field: str, reconstruct: bool) -> None:
    """Advertise nonempty colors while preserving omission and revision clears."""
    model = construction_model(AuthoringGridIntent) if reconstruct else AuthoringGridIntent
    validator = Draft202012Validator(model.model_json_schema())
    invalid = {field: ""}
    assert list(validator.iter_errors(invalid))
    with pytest.raises(ValidationError):
        model.model_validate(invalid)
    for payload in ({}, {field: "#222222"}, {field: "black"}):
        assert not list(validator.iter_errors(payload))
        assert model.model_validate(payload).model_dump(exclude_unset=True) == payload
    clear = {field: {"operation": "clear"}}
    if reconstruct:
        with pytest.raises(ValidationError):
            model.model_validate(clear)
    else:
        assert not list(validator.iter_errors(clear))
        assert model.model_validate(clear).model_dump(exclude_unset=True) == clear
