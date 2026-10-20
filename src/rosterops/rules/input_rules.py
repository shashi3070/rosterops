"""Group A — Input and schema validation rule specifications."""

from __future__ import annotations

from rosterops.models import InputMode, Severity
from rosterops.rules.base import register_rule

__all__ = ["ING_001", "ING_002", "ING_003", "SCH_001", "SCH_002", "SCH_003", "SCH_004", "SCH_005"]

_SP = frozenset({InputMode.SNAPSHOT, InputMode.PROCESS})
_GROUP = "input"

ING_001 = register_rule(
    id="ING-001",
    name="Input file exists and is readable",
    description=(
        "Every configured input path must exist and open successfully; a missing "
        "required input fails the run, a missing optional input is skipped with a note."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

ING_002 = register_rule(
    id="ING-002",
    name="File format is supported (incl. missing `[excel]` extra)",
    description=(
        "Input extension must be one of the supported formats (csv, parquet, or "
        "excel with the rosterops[excel] extra installed); otherwise the run fails "
        "with an actionable message listing supported formats."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

ING_003 = register_rule(
    id="ING-003",
    name="Expected worksheet exists",
    description=(
        "When an Excel input names a worksheet, that sheet must exist in the "
        "workbook; empty workbooks and empty sheets are reported with file context."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

SCH_001 = register_rule(
    id="SCH-001",
    name="Required columns present",
    description=(
        "After mapping resolution, every required canonical field for the input "
        "role must resolve to a source column; unresolved fields reject that "
        "input role with an explanation of the missing column."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

SCH_002 = register_rule(
    id="SCH-002",
    name="Column types are valid (parse failures located by row)",
    description=(
        "Values in typed columns (dates, numbers, booleans) must parse under the "
        "configured formats; failures are reported with file, sheet, and row."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

SCH_003 = register_rule(
    id="SCH-003",
    name="Required fields are populated",
    description=(
        "Fields that must be non-null for a usable record (identifiers, effective "
        "dates) are flagged with file, sheet, row, and field context when empty."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

SCH_004 = register_rule(
    id="SCH-004",
    name="Configured categorical values are valid",
    description=(
        "Categorical fields with configured allowed values (statuses, assignment "
        "types) flag unrecognized values; they are never silently rewritten to a "
        "guessed canonical value."
    ),
    default_severity=Severity.WARNING,
    modes=_SP,
    group=_GROUP,
)

SCH_005 = register_rule(
    id="SCH-005",
    name="Source-to-canonical mapping is unambiguous",
    description=(
        "Two source columns mapped to one canonical field without an explicit "
        "merge strategy rejects the configuration as ambiguous."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)
