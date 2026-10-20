"""Strict, versioned configuration for rosterops.

Separates source mapping from business policy. Parsed with ``yaml.safe_load``
only — configuration can never execute code, shell commands, or imports.
Precedence: built-in defaults < config file < CLI overrides (merged as raw
layers by :meth:`RosterConfig.from_layers` before validation).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rosterops.exceptions import ConfigError
from rosterops.models import (
    BASELINE_FIELDS,
    KNOWN_CONFLICT_POLICIES,
    KNOWN_INPUT_ROLES,
    ROLE_FIELDS,
    Grain,
    Severity,
    TerminationDateSemantics,
)
from rosterops.rules import all_rule_ids, get_rule

__all__ = ["RosterConfig"]


class InputDateSemantics(BaseModel):
    """Per-source date convention overrides."""

    model_config = ConfigDict(extra="forbid")

    interval_end: Literal["exclusive", "inclusive"] = "exclusive"


class InputRoleConfig(BaseModel):
    """Mapping of one input role's source file onto canonical fields."""

    model_config = ConfigDict(extra="forbid")

    path: str | None = None
    format: Literal["csv", "excel", "parquet"] | None = None
    sheet_name: str | None = None
    header_row: int = Field(default=0, ge=0)
    required: bool = True
    columns: dict[str, str] = Field(default_factory=dict)
    aliases: dict[str, list[str]] = Field(default_factory=dict)
    date_semantics: InputDateSemantics = Field(default_factory=InputDateSemantics)
    null_tokens: list[str] | None = None
    date_formats: dict[str, list[str]] = Field(default_factory=dict)
    value_maps: dict[str, dict[str, str]] = Field(default_factory=dict)
    allowed_values: dict[str, list[str]] = Field(default_factory=dict)


class DataConfig(BaseModel):
    """Declared input grain (decision D1)."""

    model_config = ConfigDict(extra="forbid")

    grain: Grain = Grain.EMPLOYEE_TERRITORY
    grain_keys: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_grain_keys(self) -> DataConfig:
        if self.grain is Grain.CUSTOM:
            if not self.grain_keys:
                raise ValueError(
                    "data.grain_keys must list at least one column when grain is 'custom'"
                )
        elif self.grain_keys:
            raise ValueError("data.grain_keys is only allowed when data.grain is 'custom'")
        unknown = sorted(set(self.grain_keys) - BASELINE_FIELDS)
        if unknown:
            raise ValueError(
                f"data.grain_keys contains unknown canonical field(s): {', '.join(unknown)}"
            )
        return self


class DatesConfig(BaseModel):
    """Global effective-date conventions."""

    model_config = ConfigDict(extra="forbid")

    interval_convention: Literal["half_open"] = "half_open"
    baseline_includes_effective_date: bool = True
    default_date_format: str = "%Y-%m-%d"
    termination_date_semantics: TerminationDateSemantics = (
        TerminationDateSemantics.LAST_WORKING_DAY_INCLUSIVE
    )

    @field_validator("default_date_format")
    @classmethod
    def _valid_strftime(cls, value: str) -> str:
        try:
            datetime(2000, 1, 1).strftime(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid strftime format {value!r}: {exc}") from exc
        return value


class LeavePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retains_employment_status: bool = True
    retains_home_assignment: bool = True
    coverage_required_by_default: bool = False
    allow_overlapping_leave_types: bool = False


class VacancyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    derive_only_for_required_owner_territories: bool = True
    count_leave_as_vacancy: bool = False


class EventPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reject_events_on_or_before_baseline_date: bool = True
    resolve_conflicting_same_date_events: bool | str = False

    @field_validator("resolve_conflicting_same_date_events")
    @classmethod
    def _known_policy(cls, value: bool | str) -> bool | str:
        if value is True:
            raise ValueError(
                "resolve_conflicting_same_date_events must be false or an explicit "
                f"policy name; known policies: {', '.join(KNOWN_CONFLICT_POLICIES)}"
            )
        if isinstance(value, str) and value not in KNOWN_CONFLICT_POLICIES:
            raise ValueError(
                f"unknown conflict policy {value!r}; known policies: "
                f"{', '.join(KNOWN_CONFLICT_POLICIES)}"
            )
        return value


class Policies(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_multiple_active_territories: bool = True
    max_primary_territories_per_employee: int = Field(default=1, ge=1)
    require_active_manager: bool = True
    allow_unassigned_active_employees: bool = True
    leave: LeavePolicy = Field(default_factory=LeavePolicy)
    vacancy: VacancyPolicy = Field(default_factory=VacancyPolicy)
    events: EventPolicy = Field(default_factory=EventPolicy)


class RuleOverride(BaseModel):
    """Auditable per-rule policy decision from configuration."""

    model_config = ConfigDict(extra="forbid")

    id: str
    enabled: bool = True
    severity: Severity | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _known_rule(cls, value: str) -> str:
        if value not in all_rule_ids():
            raise ValueError(f"unknown rule id {value!r} (see 'rosterops rules list')")
        return value

    @field_validator("severity", mode="before")
    @classmethod
    def _normalize_severity(cls, value: object) -> object:
        if isinstance(value, str):
            return value.lower()
        return value


def _default_formats() -> list[Literal["csv", "parquet", "json", "excel"]]:
    return ["csv", "parquet", "json"]


class OutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formats: list[Literal["csv", "parquet", "json", "excel"]] = Field(
        default_factory=_default_formats
    )
    excel_row_cap: int = Field(default=50_000, ge=1, le=1_048_576)
    fail_on_warning: bool = False

    @field_validator("formats")
    @classmethod
    def _unique_formats(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("outputs.formats contains duplicates")
        return value


class MetaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_unknown_fields: bool = False


class RosterConfig(BaseModel):
    """Root configuration document (``version: 1``)."""

    model_config = ConfigDict(extra="allow")

    version: Literal[1] = 1
    data: DataConfig = Field(default_factory=DataConfig)
    dates: DatesConfig = Field(default_factory=DatesConfig)
    policies: Policies = Field(default_factory=Policies)
    rules: list[RuleOverride] = Field(default_factory=list)
    inputs: dict[str, InputRoleConfig] = Field(default_factory=dict)
    outputs: OutputsConfig = Field(default_factory=OutputsConfig)
    meta: MetaConfig = Field(default_factory=MetaConfig)

    @model_validator(mode="after")
    def _cross_validate(self) -> RosterConfig:
        unknown = set(self.__pydantic_extra__ or {})
        if unknown and not self.meta.allow_unknown_fields:
            raise ValueError(
                f"unknown configuration field(s): {', '.join(sorted(unknown))} "
                "(set meta.allow_unknown_fields: true to permit forward-compatible fields)"
            )

        for role, cfg in self.inputs.items():
            if role not in KNOWN_INPUT_ROLES:
                raise ValueError(
                    f"unknown input role {role!r}; known roles: {', '.join(KNOWN_INPUT_ROLES)}"
                )
            allowed = ROLE_FIELDS[role]
            for label, keys in (
                ("columns", cfg.columns),
                ("aliases", cfg.aliases),
                ("value_maps", cfg.value_maps),
                ("allowed_values", cfg.allowed_values),
            ):
                bad = sorted(set(keys) - allowed)
                if bad:
                    raise ValueError(
                        f"inputs.{role}.{label}: unknown canonical field(s) for this role: "
                        f"{', '.join(bad)}"
                    )

        seen: set[str] = set()
        for override in self.rules:
            if override.id in seen:
                raise ValueError(f"duplicate rule override for {override.id!r}")
            seen.add(override.id)
            _validate_rule_params(override)
        return self

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RosterConfig:
        """Build a config from a plain mapping, wrapping validation errors."""
        if not isinstance(data, Mapping):
            raise ConfigError(f"configuration root must be a mapping, got {type(data).__name__}")
        try:
            return cls.model_validate(dict(data))
        except Exception as exc:  # pydantic ValidationError and validator ValueErrors
            raise ConfigError(_format_validation_error(exc)) from exc

    @classmethod
    def from_file(cls, path: str | Path) -> RosterConfig:
        """Load a YAML configuration file with ``yaml.safe_load`` only."""
        file_path = Path(path)
        try:
            text = file_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ConfigError(f"configuration file not found: {file_path}") from None
        except OSError as exc:
            raise ConfigError(f"configuration file not readable: {file_path}: {exc}") from exc
        except UnicodeDecodeError:
            raise ConfigError(f"configuration file is not valid UTF-8: {file_path}") from None
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ConfigError(f"invalid YAML in {file_path}: {exc}") from exc
        if loaded is None:
            raise ConfigError(f"configuration file is empty: {file_path}")
        if not isinstance(loaded, Mapping):
            raise ConfigError(
                f"configuration root must be a mapping, got {type(loaded).__name__}: {file_path}"
            )
        return cls.from_dict(loaded)

    @classmethod
    def from_layers(cls, *layers: Mapping[str, Any]) -> RosterConfig:
        """Merge raw configuration layers left-to-right (later wins), then validate.

        Precedence: built-in defaults are applied by the schema itself, so the
        first layer is the config file and subsequent layers are CLI overrides.
        """
        merged: dict[str, Any] = {}
        for layer in layers:
            merged = _merge_dicts(merged, dict(layer))
        return cls.from_dict(merged)

    def resolved_dict(self) -> dict[str, Any]:
        """JSON-serializable view of the fully resolved configuration."""
        return self.model_dump(mode="json")

    def rule_overrides(self) -> dict[str, RuleOverride]:
        """Rule overrides indexed by rule ID."""
        return {override.id: override for override in self.rules}

    def severity_for(self, rule_id: str) -> Severity:
        """Effective severity for a rule (override or default)."""
        override = self.rule_overrides().get(rule_id)
        if override is not None and override.severity is not None:
            return override.severity
        return get_rule(rule_id).default_severity

    def is_enabled(self, rule_id: str) -> bool:
        """Effective enabled state for a rule (override or default)."""
        override = self.rule_overrides().get(rule_id)
        if override is not None:
            return override.enabled
        return True


def _validate_rule_params(override: RuleOverride) -> None:
    spec = get_rule(override.id)
    for key, value in override.params.items():
        if key not in spec.params:
            raise ValueError(
                f"rule {override.id}: unknown parameter {key!r} "
                f"(declared: {', '.join(sorted(spec.params)) or 'none'})"
            )
        expected = spec.params[key]
        if not _matches_type(value, expected):
            raise ValueError(
                f"rule {override.id}: parameter {key!r} must be "
                f"{getattr(expected, '__name__', expected)}, got {type(value).__name__}"
            )


def _matches_type(value: object, expected: type) -> bool:
    if expected is bool:
        return isinstance(value, bool)
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected is float:
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected is str:
        return isinstance(value, str)
    return True


def _merge_dicts(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Recursive merge; nested dicts merge, all other values replace."""
    result = dict(base)
    for key, value in override.items():
        existing = result.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            result[key] = _merge_dicts(dict(existing), value)
        else:
            result[key] = value
    return result


def _format_validation_error(exc: Exception) -> str:
    """Compact pydantic errors into actionable single-line messages."""
    errors = getattr(exc, "errors", None)
    if callable(errors):
        parts = []
        for err in errors():
            location = ".".join(str(item) for item in err.get("loc", ()))
            message = err.get("msg", str(exc))
            parts.append(f"{location}: {message}" if location else message)
        if parts:
            return "; ".join(parts)
    return str(exc)
