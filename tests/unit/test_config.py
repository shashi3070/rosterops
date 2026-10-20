from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from rosterops.config import RosterConfig
from rosterops.exceptions import ConfigError
from rosterops.models import Grain, Severity, TerminationDateSemantics


def base_config(**overrides: Any) -> dict[str, Any]:
    config: dict[str, Any] = {"version": 1}
    config.update(overrides)
    return config


def test_defaults_apply_when_sections_absent() -> None:
    config = RosterConfig.from_dict(base_config())
    assert config.data.grain is Grain.EMPLOYEE_TERRITORY
    assert config.dates.interval_convention == "half_open"
    assert (
        config.dates.termination_date_semantics
        is TerminationDateSemantics.LAST_WORKING_DAY_INCLUSIVE
    )
    assert config.policies.leave.retains_employment_status is True
    assert config.policies.vacancy.derive_only_for_required_owner_territories is True
    assert config.policies.events.reject_events_on_or_before_baseline_date is True
    assert config.rules == []
    assert config.outputs.formats == ["csv", "parquet", "json"]


def test_example_config_loads(example_config_path: Path) -> None:
    config = RosterConfig.from_file(example_config_path)
    assert config.version == 1
    assert config.data.grain is Grain.EMPLOYEE_TERRITORY
    assert set(config.inputs) >= {"baseline", "transfers", "terminations"}
    assert config.inputs["baseline"].columns["employee_id"] == "Employee Number"
    assert config.inputs["baseline"].sheet_name == "Roster"
    overrides = config.rule_overrides()
    assert overrides["TRF-002"].severity is Severity.ERROR
    assert overrides["LOA-007"].params == {"coverage_required": False}
    assert overrides["TER-005"].params == {"grace_days": 0}
    assert config.severity_for("LOA-007") is Severity.WARNING
    assert config.severity_for("TRF-001") is Severity.ERROR  # no override
    assert config.is_enabled("TRF-002") is True


def test_unknown_top_level_field_rejected() -> None:
    with pytest.raises(ConfigError, match="unknown configuration field"):
        RosterConfig.from_dict(base_config(surprise=True))


def test_unknown_top_level_field_allowed_when_meta_permits() -> None:
    config = RosterConfig.from_dict(
        base_config(future_section={"x": 1}, meta={"allow_unknown_fields": True})
    )
    assert config.meta.allow_unknown_fields is True


def test_nested_unknown_field_always_rejected() -> None:
    with pytest.raises(ConfigError):
        RosterConfig.from_dict(base_config(policies={"not_a_policy": True}))


def test_invalid_version_rejected() -> None:
    with pytest.raises(ConfigError, match="version"):
        RosterConfig.from_dict({"version": 2})


def test_invalid_severity_rejected() -> None:
    with pytest.raises(ConfigError, match="severity"):
        RosterConfig.from_dict(base_config(rules=[{"id": "TRF-002", "severity": "fatal"}]))


def test_severity_is_case_insensitive() -> None:
    config = RosterConfig.from_dict(base_config(rules=[{"id": "TRF-002", "severity": "ERROR"}]))
    assert config.rules[0].severity is Severity.ERROR


def test_unknown_rule_id_rejected() -> None:
    with pytest.raises(ConfigError, match="ZZZ-999"):
        RosterConfig.from_dict(base_config(rules=[{"id": "ZZZ-999"}]))


def test_duplicate_rule_override_rejected() -> None:
    with pytest.raises(ConfigError, match="duplicate rule override"):
        RosterConfig.from_dict(
            base_config(rules=[{"id": "TRF-002"}, {"id": "TRF-002", "enabled": False}])
        )


def test_unknown_rule_parameter_rejected() -> None:
    with pytest.raises(ConfigError, match="unknown parameter"):
        RosterConfig.from_dict(base_config(rules=[{"id": "TER-005", "params": {"nonsense": 1}}]))


def test_rule_parameter_wrong_type_rejected() -> None:
    with pytest.raises(ConfigError, match="grace_days"):
        RosterConfig.from_dict(
            base_config(rules=[{"id": "TER-005", "params": {"grace_days": "high"}}])
        )
    with pytest.raises(ConfigError, match="grace_days"):
        # bool is not an int for rule parameters.
        RosterConfig.from_dict(
            base_config(rules=[{"id": "TER-005", "params": {"grace_days": True}}])
        )


def test_rule_parameter_bool_correct_type() -> None:
    config = RosterConfig.from_dict(
        base_config(rules=[{"id": "LOA-007", "params": {"coverage_required": True}}])
    )
    assert config.rules[0].params["coverage_required"] is True


def test_custom_grain_requires_keys() -> None:
    with pytest.raises(ConfigError, match="grain_keys"):
        RosterConfig.from_dict(base_config(data={"grain": "custom"}))


def test_grain_keys_only_for_custom_grain() -> None:
    with pytest.raises(ConfigError, match="grain_keys"):
        RosterConfig.from_dict(
            base_config(data={"grain": "employee", "grain_keys": ["employee_id"]})
        )


def test_grain_keys_must_be_known_canonical_fields() -> None:
    with pytest.raises(ConfigError, match="unknown canonical field"):
        RosterConfig.from_dict(
            base_config(data={"grain": "custom", "grain_keys": ["favorite_color"]})
        )


def test_custom_grain_with_valid_keys() -> None:
    config = RosterConfig.from_dict(
        base_config(
            data={
                "grain": "custom",
                "grain_keys": ["employee_id", "territory_id", "is_primary"],
            }
        )
    )
    assert config.data.grain is Grain.CUSTOM


def test_invalid_date_format_rejected() -> None:
    with pytest.raises(ConfigError, match="strftime"):
        RosterConfig.from_dict(base_config(dates={"default_date_format": "%Q"}))


def test_invalid_termination_semantics_rejected() -> None:
    with pytest.raises(ConfigError, match="termination_date_semantics"):
        RosterConfig.from_dict(base_config(dates={"termination_date_semantics": "sometime"}))


def test_conflict_policy_must_be_false_or_known_name() -> None:
    with pytest.raises(ConfigError, match="explicit"):
        RosterConfig.from_dict(
            base_config(policies={"events": {"resolve_conflicting_same_date_events": True}})
        )
    with pytest.raises(ConfigError, match="unknown conflict policy"):
        RosterConfig.from_dict(
            base_config(policies={"events": {"resolve_conflicting_same_date_events": "vibes"}})
        )
    config = RosterConfig.from_dict(
        base_config(
            policies={"events": {"resolve_conflicting_same_date_events": "effective_then_source"}}
        )
    )
    assert config.policies.events.resolve_conflicting_same_date_events == "effective_then_source"


def test_unknown_input_role_rejected() -> None:
    with pytest.raises(ConfigError, match="unknown input role"):
        RosterConfig.from_dict(base_config(inputs={"weather": {"path": "x.csv"}}))


def test_input_column_key_must_be_canonical_for_role() -> None:
    with pytest.raises(ConfigError, match="unknown canonical field"):
        RosterConfig.from_dict(
            base_config(inputs={"transfers": {"columns": {"territory_id": "Terr"}}})
        )
    with pytest.raises(ConfigError, match="unknown canonical field"):
        RosterConfig.from_dict(
            base_config(inputs={"baseline": {"columns": {"to_territory_id": "New Terr"}}})
        )


def test_negative_header_row_rejected() -> None:
    with pytest.raises(ConfigError, match="header_row"):
        RosterConfig.from_dict(base_config(inputs={"baseline": {"header_row": -1}}))


def test_invalid_interval_convention_rejected() -> None:
    with pytest.raises(ConfigError, match="interval_convention"):
        RosterConfig.from_dict(base_config(dates={"interval_convention": "closed"}))


def test_missing_config_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        RosterConfig.from_file(tmp_path / "nope.yaml")


def test_empty_config_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("# nothing here\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="empty"):
        RosterConfig.from_file(path)


def test_non_mapping_config_root_raises(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        RosterConfig.from_file(path)


def test_arbitrary_python_yaml_tag_rejected(tmp_path: Path) -> None:
    path = tmp_path / "evil.yaml"
    path.write_text("version: !!python/object/apply:os.system ['echo hi']\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid YAML"):
        RosterConfig.from_file(path)


def test_invalid_utf8_config_raises(tmp_path: Path) -> None:
    path = tmp_path / "binary.yaml"
    path.write_bytes(b"\xff\xfe\x00\x00version: 1\n")
    with pytest.raises(ConfigError, match="UTF-8"):
        RosterConfig.from_file(path)


def test_layer_precedence_defaults_file_cli() -> None:
    file_layer = {
        "version": 1,
        "dates": {"termination_date_semantics": "first_inactive_day"},
        "policies": {"max_primary_territories_per_employee": 2},
    }
    cli_layer = {"policies": {"max_primary_territories_per_employee": 3}}
    config = RosterConfig.from_layers(file_layer, cli_layer)
    # CLI layer wins over file layer...
    assert config.policies.max_primary_territories_per_employee == 3
    # ...file layer wins over defaults...
    assert config.dates.termination_date_semantics is TerminationDateSemantics.FIRST_INACTIVE_DAY
    # ...defaults survive where untouched.
    assert config.dates.baseline_includes_effective_date is True


def test_layer_merge_does_not_mutate_inputs() -> None:
    file_layer = {"version": 1, "policies": {"leave": {"coverage_required_by_default": True}}}
    cli_layer = {"policies": {"require_active_manager": False}}
    original = deepcopy(file_layer)
    RosterConfig.from_layers(file_layer, cli_layer)
    assert file_layer == original


def test_resolved_dict_is_json_serializable(example_config_path: Path) -> None:
    import json

    config = RosterConfig.from_file(example_config_path)
    dumped = json.dumps(config.resolved_dict())
    assert '"grain": "employee_territory"' in dumped


def test_outputs_formats_must_be_unique() -> None:
    with pytest.raises(ConfigError, match="duplicate"):
        RosterConfig.from_dict(base_config(outputs={"formats": ["csv", "csv"]}))


def test_disabled_rule_override() -> None:
    config = RosterConfig.from_dict(base_config(rules=[{"id": "TER-005", "enabled": False}]))
    assert config.is_enabled("TER-005") is False
    assert config.is_enabled("TER-001") is True
