"""Pure identity, ownership, and runtime-handle tests for CM-13."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from wellplot.authoring_program.builders import (
    AnnotationHandle,
    BindingHandle,
    FillHandle,
    HandleBuilder,
    ReportHandle,
    SectionHandle,
)
from wellplot.authoring_program.errors import (
    ProgramNameError,
    ProgramPolicyError,
    ProgramTypeError,
)
from wellplot.authoring_program.ids import IdAllocator, slugify_id_hint
from wellplot.authoring_program.interpreter import interpret_authoring_program
from wellplot.authoring_program.models import AuthoringProgram, ProgramSource
from wellplot.authoring_program.runtime import (
    HandleMethodRegistry,
    RootMethodRegistry,
    RuntimeEnvironment,
    RuntimeHandle,
    is_runtime_handle,
    runtime_value_item_count,
)


def _builder(builder_id: str = "builder-a") -> HandleBuilder:
    """Create one deterministic provenance context for identity tests."""
    return HandleBuilder(builder_id=builder_id)


def _track(builder: HandleBuilder, section_id: str, track_hint: str = "combo") -> object:
    """Issue one report, adopted section, and new typed track handle."""
    report = builder.create_report()
    section = builder.adopt_section(report, section_id)
    return builder.create_track(section, track_hint)


@pytest.mark.parametrize(
    ("value", "fallback", "expected"),
    [
        (" Gamma / Ray! ", "item", "gamma-ray"),
        ("A___B...C", "item", "a-b-c"),
        ("Cafe\u0301", "item", "cafe"),
        ("---", "item", "item"),
        (None, "item", "item"),
    ],
)
def test_slugify_id_hint_is_locale_independent_and_uses_a_fixed_fallback(
    value: str | None,
    fallback: str,
    expected: str,
) -> None:
    """New identity seeds are deterministic while adopted IDs remain exact."""
    assert slugify_id_hint(value, fallback=fallback) == expected

    with pytest.raises(ProgramTypeError):
        slugify_id_hint(42, fallback=fallback)  # type: ignore[arg-type]


def test_reservation_sets_choose_first_free_suffix_without_hidden_counters() -> None:
    """Existing high suffixes do not advance an invisible allocation counter."""
    allocator = IdAllocator()

    assert [allocator.allocate_section("main") for _ in range(3)] == ["main", "main.2", "main.3"]

    allocator = IdAllocator(section_ids=("main",))
    assert [allocator.allocate_track("main", "combo") for _ in range(2)] == ["combo", "combo.2"]

    allocator = IdAllocator(section_ids=("main",))
    allocator.adopt_track("main", "combo")
    allocator.adopt_binding("main.combo.GR")
    assert allocator.allocate_binding("main", "combo", channel="GR") == "main.combo.GR.2"

    allocator.adopt_binding("main.combo.GR.7")
    assert allocator.allocate_binding("main", "combo", channel="GR") == "main.combo.GR.3"

    allocator = IdAllocator(section_ids=("main",))
    allocator.adopt_track("main", "combo")
    allocator.adopt_binding("main.combo.GR")
    allocator.adopt_binding("main.combo.GR.7")
    assert allocator.allocate_binding("main", "combo", channel="GR") == "main.combo.GR.2"


def test_newly_allocated_sections_immediately_accept_section_scoped_tracks() -> None:
    """Allocation initializes the local track namespace just like section adoption."""
    allocator = IdAllocator()

    section_id = allocator.allocate_section("main")

    assert allocator.allocate_track(section_id, "combo") == "combo"


def test_track_scope_is_local_to_sections_and_binding_scope_is_document_wide() -> None:
    """Identical local track IDs are legal while binding IDs remain global."""
    allocator = IdAllocator(section_ids=("main", "repeat"))

    assert allocator.allocate_track("main", "combo") == "combo"
    assert allocator.allocate_track("repeat", "combo") == "combo"
    assert allocator.allocate_binding("main", "combo", channel="GR") == "main.combo.GR"
    assert allocator.allocate_binding("repeat", "combo", channel="GR") == "repeat.combo.GR"
    assert (
        allocator.allocate_binding("main", "combo", channel="CCL", id_hint="advisory")
        == "main.combo.CCL"
    )
    assert allocator.binding_is_reserved("main.combo.GR")
    assert allocator.binding_is_reserved("repeat.combo.GR")


def test_equivalent_reservation_and_creation_sequences_produce_equivalent_ids() -> None:
    """ID stability is defined by semantic reservation and creation order."""

    def allocate_sequence() -> tuple[str, str, str, str]:
        allocator = IdAllocator(section_ids=("main",))
        track = allocator.allocate_track("main", "combo")
        first = allocator.allocate_binding("main", track, channel="GR")
        second = allocator.allocate_binding("main", track, channel="GR")
        leaf = allocator.allocate_leaf("main", track, leaf_kind="fill", id_hint="gas crossover")
        return track, first, second, leaf

    assert allocate_sequence() == allocate_sequence()


def test_handle_builder_issues_typed_handles_and_adoption_is_idempotent() -> None:
    """Adopting identities preserves exact IDs without allocating replacements."""
    builder = _builder()
    report = builder.create_report()
    section = builder.adopt_section(report, "main")
    track = builder.adopt_track(section, "combo")
    binding = builder.adopt_binding(track, "main.combo.GR")
    fill = builder.adopt_fill(track, "main.combo.fill.gas")
    annotation = builder.adopt_annotation(track, "main.combo.annotation.note")

    assert builder.adopt_section(report, "main") is section
    assert builder.adopt_track(section, "combo") is track
    assert builder.adopt_binding(track, "main.combo.GR") is binding
    assert builder.adopt_fill(track, "main.combo.fill.gas") is fill
    assert builder.adopt_annotation(track, "main.combo.annotation.note") is annotation
    assert builder.create_binding(track, channel="GR").binding_id == "main.combo.GR.2"
    assert builder.create_binding(track, channel="GR").binding_id == "main.combo.GR.3"
    assert isinstance(binding, BindingHandle)
    assert isinstance(fill, FillHandle)
    assert isinstance(annotation, AnnotationHandle)


def test_handle_builder_rejects_foreign_wrong_parent_and_unknown_identities() -> None:
    """Provenance and ownership failures stay in the typed program-error taxonomy."""
    builder = _builder()
    report = builder.create_report()
    main = builder.adopt_section(report, "main")
    repeat = builder.adopt_section(report, "repeat")
    main_track = builder.create_track(main, "combo")
    repeat_track = builder.create_track(repeat, "combo")
    binding = builder.create_binding(main_track, channel="GR")
    fill = builder.create_fill(main_track, "gas")
    annotation = builder.create_annotation(main_track, "note")

    with pytest.raises(ProgramPolicyError, match="does not belong"):
        builder.validate_track_parent(repeat, main_track)
    for leaf in (binding, fill, annotation):
        with pytest.raises(ProgramPolicyError, match="does not belong"):
            builder.validate_leaf_parent(repeat_track, leaf)

    other_builder = _builder("builder-b")
    with pytest.raises(ProgramNameError, match="different identity builder"):
        other_builder.create_section(report, "foreign")

    forged = SectionHandle(
        token="builder-a:section:report:unknown",
        kind="section",
        builder_id="builder-a",
        report_token=report.token,
        section_id="unknown",
    )
    with pytest.raises(ProgramNameError, match="not issued or reserved"):
        builder.create_track(forged, "combo")

    with pytest.raises(ProgramTypeError, match="incompatible"):
        builder.validate_track_parent(main, main)


def test_typed_handles_are_safe_runtime_values_but_untrusted_lookalikes_are_not() -> None:
    """CM-13 subclasses cross CM-12's registry boundary without opening it broadly."""
    builder = _builder()
    track = _track(builder, "main")
    assert is_runtime_handle(track)
    assert runtime_value_item_count(track) == 1

    @dataclass(frozen=True, slots=True)
    class Lookalike:
        token: str
        kind: str
        payload: object

    class UntrustedRuntimeHandle(RuntimeHandle):
        pass

    with pytest.raises(ProgramTypeError):
        runtime_value_item_count(Lookalike(token="track:1", kind="track", payload=object()))
    with pytest.raises(ProgramTypeError):
        runtime_value_item_count(UntrustedRuntimeHandle(token="untrusted", kind="track"))


def test_typed_handles_dispatch_through_the_existing_explicit_runtime_registry() -> None:
    """CM-13 handle types do not alter CM-12's registry-only dispatch mechanism."""
    builder = _builder()
    report = builder.create_report()
    section = builder.adopt_section(report, "main")
    track = builder.create_track(section, "combo")
    runtime = RuntimeEnvironment(
        root_methods=RootMethodRegistry(methods={"section": lambda _args, _kwargs: section}),
        handle_methods=HandleMethodRegistry(
            methods={("section", "track"): lambda _args, _kwargs: track}
        ),
    )
    program = AuthoringProgram(
        source=ProgramSource(
            text="section = wp.section()\ntrack = section.track()\n",
            logical_name="typed-handles.wpa",
        )
    )

    result = interpret_authoring_program(program, runtime)

    assert result.journal[0].result_handle == section.token
    assert result.journal[1].result_handle == track.token
    assert result.metrics.created_objects == 2


def test_allocator_rejects_unknown_parent_scopes_without_python_key_errors() -> None:
    """Unreserved parent identities are explicit program-name diagnostics."""
    allocator = IdAllocator()

    with pytest.raises(ProgramNameError, match="has not been reserved"):
        allocator.allocate_track("main", "combo")
    with pytest.raises(ProgramNameError, match="has not been reserved"):
        allocator.allocate_binding("main", "combo", channel="GR")
    with pytest.raises(ProgramNameError, match="has not been reserved"):
        allocator.allocate_leaf("main", "combo", leaf_kind="fill")


def test_typed_handle_constructors_keep_identity_fields_immutable() -> None:
    """Handles carry identity metadata only and cannot gain mutable state fields."""
    report = ReportHandle(
        token="builder-a:report:report",
        kind="report",
        builder_id="builder-a",
        report_id="report",
    )

    with pytest.raises(AttributeError):
        report.report_id = "changed"  # type: ignore[misc]
