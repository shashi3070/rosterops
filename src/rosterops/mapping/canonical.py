"""Source-to-canonical column mapping, typing, and normalization.

Given a :class:`~rosterops.io.raw.RawTable` and one input role's configuration,
:func:`map_to_canonical` produces a canonical frame with lineage columns and a
list of located findings. Rules raised here:

- ``SCH-005`` mapping ambiguity (two sources -> one canonical without a merge).
- ``SCH-001`` required canonical columns missing after alias resolution.
- ``SCH-002`` values that fail typed parsing (located by row/column).
- ``SCH-003`` required fields that are empty on a row.
- ``SCH-004`` categorical values outside the configured/allowed set.
- ``ID-005`` whitespace/trim-induced collisions (warning, never auto-merged).

No row is ever dropped: a cell that fails typed parsing becomes null in the
canonical frame and produces a located ``SCH-002`` finding for that row.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from rosterops.config import InputRoleConfig
from rosterops.domain.dates import DEFAULT_DATE_FORMATS, parse_date
from rosterops.io.raw import RawTable
from rosterops.models import REQUIRED_EVENT_FIELDS
from rosterops.rules.base import Finding
from rosterops.rules.identifier_rules import ID_005
from rosterops.rules.input_rules import SCH_001, SCH_002, SCH_003, SCH_004, SCH_005

__all__ = ["DEFAULT_NULL_TOKENS", "MappedInput", "map_to_canonical"]

#: Default null tokens applied when a role config does not override them.
DEFAULT_NULL_TOKENS: tuple[str, ...] = ("", "N/A", "n/a", "NA", "NULL", "null", "None", "-")

_TYPED_DATE_FIELDS = frozenset(
    {
        "effective_from",
        "effective_to",
        "employment_start_date",
        "employment_end_date",
        "effective_date",
        "recorded_date",
        "leave_start_date",
        "leave_end_date",
        "coverage_start_date",
        "coverage_end_date",
    }
)
_TYPED_BOOLEAN_FIELDS = frozenset(
    {
        "is_primary",
        "requires_primary_owner",
        "coverage_required_during_leave",
        "is_primary_coverage",
    }
)
_TYPED_INTEGER_FIELDS = frozenset({"max_assignees"})
_TYPED_LIST_FIELDS = frozenset({"allowed_roles", "allowed_successor_role_codes"})

_BOOLEAN_TRUE = frozenset({"true", "t", "yes", "y", "1"})
_BOOLEAN_FALSE = frozenset({"false", "f", "no", "n", "0"})
_LIST_SEPARATORS = (";", "|")

#: Fields required to be populated per role, beyond the documented event set.
_ALWAYS_REQUIRED_ENTITIES: frozenset[str] = frozenset({"employee_id"})


@dataclass(frozen=True, slots=True)
class MappedInput:
    """Canonical frame + findings for one input role."""

    role: str
    frame: pl.DataFrame
    findings: tuple[Finding, ...]
    resolved_fields: frozenset[str]
    unused_columns: tuple[str, ...]
    failed: bool = False


def map_to_canonical(
    role: str,
    raw: RawTable,
    cfg: InputRoleConfig,
    *,
    source_file: str,
    source_sheet: str | None,
    first_data_row: int,
) -> MappedInput:
    """Map a raw table onto a role's canonical schema with located findings."""
    frame = raw.frame
    findings: list[Finding] = []
    source_columns = list(frame.columns)

    resolved, resolution_findings = _resolve_columns(
        role, cfg, source_columns, source_file, source_sheet, first_data_row
    )
    findings.extend(resolution_findings)
    if resolved is None:
        return MappedInput(
            role=role,
            frame=pl.DataFrame(),
            findings=tuple(findings),
            resolved_fields=frozenset(),
            unused_columns=tuple(source_columns),
            failed=True,
        )

    null_tokens = tuple(cfg.null_tokens) if cfg.null_tokens is not None else DEFAULT_NULL_TOKENS

    # 1) string pass: select + trim + null-token normalization.
    out = frame.select(
        [
            pl.col(src).cast(pl.String, strict=False).alias(canonical)
            for canonical, src in resolved.items()
        ]
    )
    out = _apply_null_tokens(_apply_trim(out), null_tokens)

    # 2) typed pass per canonical field, recording parse failures by row.
    for canonical in resolved:
        if canonical in _TYPED_DATE_FIELDS:
            out, failures = _to_date(out, canonical, cfg, first_data_row, source_file, source_sheet)
            findings.extend(failures)
        elif canonical in _TYPED_BOOLEAN_FIELDS:
            out, failures = _to_boolean(out, canonical, first_data_row, source_file, source_sheet)
            findings.extend(failures)
        elif canonical in _TYPED_INTEGER_FIELDS:
            out, failures = _to_integer(out, canonical, first_data_row, source_file, source_sheet)
            findings.extend(failures)
        elif canonical in _TYPED_LIST_FIELDS:
            out = _to_list(out, canonical)

    # 3) value maps: normalize known source codes -> canonical codes.
    for canonical, mapping in cfg.value_maps.items():
        if canonical in out.columns:
            out = out.with_columns(pl.col(canonical).replace(mapping).alias(canonical))

    # 4) categorical validation (SCH-004): warn, never rewrite.
    for canonical, allowed in cfg.allowed_values.items():
        if canonical in out.columns:
            findings.extend(
                _validate_categorical(
                    out, canonical, allowed, source_file, source_sheet, first_data_row
                )
            )

    # 5) required-populated (SCH-003).
    findings.extend(
        _check_required_populated(
            out, role, set(resolved), source_file, source_sheet, first_data_row
        )
    )

    # 6) ID-005 trim collisions on identifier columns.
    findings.extend(
        _check_trim_collisions(
            frame, resolved, source_file, source_sheet, first_data_row, null_tokens
        )
    )

    # 7) lineage columns (deterministic, 1-based source data rows).
    row_count = out.height
    out = out.with_columns(
        [
            pl.lit(source_file).alias("source_file"),
            pl.lit(source_sheet).alias("source_sheet"),
            (pl.int_range(0, row_count, dtype=pl.Int64) + first_data_row).alias("source_row"),
        ]
    )

    used = set(resolved.values())
    unused = tuple(c for c in source_columns if c not in used)
    return MappedInput(
        role=role,
        frame=out,
        findings=tuple(findings),
        resolved_fields=frozenset(resolved),
        unused_columns=unused,
        failed=False,
    )


def _resolve_columns(
    role: str,
    cfg: InputRoleConfig,
    source_columns: list[str],
    source_file: str,
    source_sheet: str | None,
    first_data_row: int,
) -> tuple[dict[str, str] | None, list[Finding]]:
    """Resolve canonical -> source column using explicit mapping + aliases.

    Returns ``(resolution, findings)``; ``resolution`` is ``None`` when the
    mapping is ambiguous (``SCH-005``).
    """
    findings: list[Finding] = []
    lowered: dict[str, str] = {}
    for column in source_columns:
        lowered.setdefault(column.lower(), column)

    resolution: dict[str, str] = {}

    # Explicit mappings first (canonical -> source name).
    for canonical, source in cfg.columns.items():
        actual = source if source in source_columns else lowered.get(source.lower())
        if actual is None:
            findings.append(
                Finding.from_spec(
                    SCH_001,
                    f"mapped source column {source!r} for canonical field {canonical!r} "
                    f"not found in {source_file!r}",
                    source_file=source_file,
                    source_sheet=source_sheet,
                    source_column=canonical,
                    expected_value=source,
                    suggested_action="add the column to the input or fix inputs.<role>.columns",
                )
            )
            continue
        resolution[canonical] = actual

    # Alias fallbacks for canonical fields not explicitly mapped.
    for canonical, aliases in cfg.aliases.items():
        if canonical in resolution:
            continue
        for alias in aliases:
            actual = alias if alias in source_columns else lowered.get(alias.lower())
            if actual is not None:
                resolution[canonical] = actual
                break

    # SCH-005: two source columns mapped to one canonical field.
    seen_targets: dict[str, str] = {}
    for canonical, source in list(resolution.items()):
        if source in seen_targets:
            findings.append(
                Finding.from_spec(
                    SCH_005,
                    f"canonical field {canonical!r} and {seen_targets[source]!r} both map to "
                    f"source column {source!r}; mapping is ambiguous",
                    source_file=source_file,
                    source_sheet=source_sheet,
                    source_column=canonical,
                    actual_value=source,
                    suggested_action="map each source column to a single canonical field",
                )
            )
            return None, findings
        seen_targets[source] = canonical

    return resolution, findings


def _apply_trim(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns(
        [pl.col(name).str.strip_chars().alias(name) for name in frame.columns]
    )


def _apply_null_tokens(frame: pl.DataFrame, null_tokens: tuple[str, ...]) -> pl.DataFrame:
    if not null_tokens:
        return frame
    return frame.with_columns(
        [
            pl.when(pl.col(name).is_in(list(null_tokens)))
            .then(pl.lit(None, dtype=pl.String))
            .otherwise(pl.col(name))
            .alias(name)
            for name in frame.columns
        ]
    )


def _to_date(
    frame: pl.DataFrame,
    column: str,
    cfg: InputRoleConfig,
    first_data_row: int,
    source_file: str,
    source_sheet: str | None,
) -> tuple[pl.DataFrame, list[Finding]]:
    formats = tuple(cfg.date_formats.get(column, list(DEFAULT_DATE_FORMATS)))
    findings: list[Finding] = []
    parsed: list[object] = []
    for index, value in enumerate(frame[column].to_list()):
        result = parse_date(value, formats)
        parsed.append(result)
        if result is None and value is not None:
            findings.append(
                Finding.from_spec(
                    SCH_002,
                    f"value {value!r} in column {column!r} is not a valid date",
                    source_file=source_file,
                    source_sheet=source_sheet,
                    source_row=first_data_row + index,
                    source_column=column,
                    actual_value=str(value),
                    expected_value=" / ".join(formats),
                    suggested_action="fix the cell or add its format to inputs.<role>.date_formats",
                )
            )
    out = frame.with_columns(pl.Series(column, parsed, dtype=pl.Date))
    return out, findings


def _to_boolean(
    frame: pl.DataFrame,
    column: str,
    first_data_row: int,
    source_file: str,
    source_sheet: str | None,
) -> tuple[pl.DataFrame, list[Finding]]:
    findings: list[Finding] = []
    parsed: list[object] = []
    for index, value in enumerate(frame[column].to_list()):
        result = _parse_boolean(value)
        parsed.append(result)
        if result is None and value is not None:
            findings.append(
                Finding.from_spec(
                    SCH_002,
                    f"value {value!r} in column {column!r} is not a valid boolean",
                    source_file=source_file,
                    source_sheet=source_sheet,
                    source_row=first_data_row + index,
                    source_column=column,
                    actual_value=str(value),
                    expected_value="true/false, yes/no, 1/0",
                )
            )
    out = frame.with_columns(pl.Series(column, parsed, dtype=pl.Boolean))
    return out, findings


def _parse_boolean(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _BOOLEAN_TRUE:
        return True
    if text in _BOOLEAN_FALSE:
        return False
    return None


def _to_integer(
    frame: pl.DataFrame,
    column: str,
    first_data_row: int,
    source_file: str,
    source_sheet: str | None,
) -> tuple[pl.DataFrame, list[Finding]]:
    findings: list[Finding] = []
    parsed: list[object] = []
    for index, value in enumerate(frame[column].to_list()):
        result = _parse_integer(value)
        parsed.append(result)
        if result is None and value is not None:
            findings.append(
                Finding.from_spec(
                    SCH_002,
                    f"value {value!r} in column {column!r} is not a valid integer",
                    source_file=source_file,
                    source_sheet=source_sheet,
                    source_row=first_data_row + index,
                    source_column=column,
                    actual_value=str(value),
                )
            )
    out = frame.with_columns(pl.Series(column, parsed, dtype=pl.Int64))
    return out, findings


def _parse_integer(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            as_float = float(text)
        except ValueError:
            return None
        return int(as_float) if as_float.is_integer() else None


def _to_list(frame: pl.DataFrame, column: str) -> pl.DataFrame:
    def split(value: object) -> list[str] | None:
        if value is None:
            return None
        text = str(value)
        for sep in _LIST_SEPARATORS:
            if sep in text:
                return [part.strip() for part in text.split(sep) if part.strip()]
        return [text.strip()] if text.strip() else None

    values = [split(v) for v in frame[column].to_list()]
    return frame.with_columns(pl.Series(column, values, dtype=pl.List(pl.String)))


def _validate_categorical(
    frame: pl.DataFrame,
    column: str,
    allowed: list[str],
    source_file: str,
    source_sheet: str | None,
    first_data_row: int,
) -> list[Finding]:
    allowed_set = set(allowed)
    findings: list[Finding] = []
    for index, value in enumerate(frame[column].to_list()):
        if value is None:
            continue
        if value not in allowed_set:
            findings.append(
                Finding.from_spec(
                    SCH_004,
                    f"value {value!r} in column {column!r} is not an allowed categorical value",
                    source_file=source_file,
                    source_sheet=source_sheet,
                    source_row=first_data_row + index,
                    source_column=column,
                    actual_value=str(value),
                    expected_value=", ".join(allowed),
                )
            )
    return findings


def _check_required_populated(
    frame: pl.DataFrame,
    role: str,
    resolved_fields: set[str],
    source_file: str,
    source_sheet: str | None,
    first_data_row: int,
) -> list[Finding]:
    required = set(REQUIRED_EVENT_FIELDS.get(role, frozenset()))
    required |= _ALWAYS_REQUIRED_ENTITIES & resolved_fields
    required &= resolved_fields
    findings: list[Finding] = []
    if frame.height == 0:
        return findings
    for column in sorted(required):
        for index, value in enumerate(frame[column].to_list()):
            if value is None or (isinstance(value, str) and not value.strip()):
                findings.append(
                    Finding.from_spec(
                        SCH_003,
                        f"required field {column!r} is empty",
                        source_file=source_file,
                        source_sheet=source_sheet,
                        source_row=first_data_row + index,
                        source_column=column,
                    )
                )
    return findings


def _check_trim_collisions(
    frame: pl.DataFrame,
    resolved: dict[str, str],
    source_file: str,
    source_sheet: str | None,
    first_data_row: int,
    null_tokens: tuple[str, ...],
) -> list[Finding]:
    findings: list[Finding] = []
    for canonical, source in resolved.items():
        raw_values = frame[source].to_list()
        # Detect distinct raw values that collapse to the same trimmed form.
        originals: dict[str, set[str]] = {}
        for value in raw_values:
            if value is None:
                continue
            raw_text = str(value)
            trimmed = raw_text.strip()
            if trimmed in null_tokens:
                continue
            originals.setdefault(trimmed, set()).add(raw_text)
        for trimmed, raws in originals.items():
            if len(raws) > 1:
                findings.append(
                    Finding.from_spec(
                        ID_005,
                        f"values {sorted(raws)} in column {canonical!r} collapse to "
                        f"{trimmed!r} after trimming",
                        source_file=source_file,
                        source_sheet=source_sheet,
                        source_column=canonical,
                        actual_value=", ".join(sorted(raws)),
                        expected_value=trimmed,
                        suggested_action="fix inconsistent whitespace or map explicitly",
                    )
                )
    return findings
