"""End-to-end ingestion for one input role.

Combines reading (:mod:`rosterops.io.readers`), canonical mapping
(:mod:`rosterops.mapping.canonical`), and the Group A rule findings into a
single :class:`IngestedInput`. Structural failures for a *required* role raise
:class:`~rosterops.exceptions.InputError`; failures for an *optional* role are
recorded as findings and the role is skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl

from rosterops.config import InputRoleConfig
from rosterops.exceptions import InputError
from rosterops.io.raw import ReadError
from rosterops.io.readers import read_raw
from rosterops.mapping.canonical import map_to_canonical
from rosterops.rules.base import Finding
from rosterops.rules.input_rules import ING_001, ING_002, ING_003

__all__ = ["IngestedInput", "ingest_role"]

_READ_ERROR_RULES = {"ING-001": ING_001, "ING-002": ING_002, "ING-003": ING_003}


@dataclass(frozen=True, slots=True)
class IngestedInput:
    """Result of ingesting one input role."""

    role: str
    frame: pl.DataFrame
    findings: tuple[Finding, ...]
    source_file: str
    skipped: bool = False
    #: Reason the role was skipped (optional roles only).
    skip_reason: str | None = None
    #: True when a structural failure makes the role unusable.
    failed: bool = False


def ingest_role(role: str, cfg: InputRoleConfig) -> IngestedInput:
    """Read + map one input role into a canonical frame with findings.

    Raises :class:`InputError` when a required role's file is missing/unreadable
    or its structure cannot be used (``ING-001``/``ING-002``/``ING-003``). A role
    with no configured ``path`` is treated as absent and skipped silently.
    """
    if cfg.path is None:
        return IngestedInput(
            role=role,
            frame=pl.DataFrame(),
            findings=(),
            source_file="",
            skipped=True,
            skip_reason="no path configured",
        )

    path = Path(cfg.path)
    try:
        table = read_raw(
            path,
            format=cfg.format,
            sheet_name=cfg.sheet_name,
            header_row=cfg.header_row,
        )
    except ReadError as exc:
        finding = _read_error_finding(exc, str(path))
        if cfg.required:
            raise InputError(exc.message) from exc
        return IngestedInput(
            role=role,
            frame=pl.DataFrame(),
            findings=(finding,),
            source_file=str(path),
            skipped=True,
            skip_reason=exc.message,
            failed=True,
        )

    mapped = map_to_canonical(
        role,
        table,
        cfg,
        source_file=str(path),
        source_sheet=table.source_sheet,
        first_data_row=table.first_data_row,
    )
    findings = list(mapped.findings)
    if mapped.failed:
        message = f"input role {role!r} could not be mapped: see findings"
        if cfg.required:
            raise InputError(message)
        return IngestedInput(
            role=role,
            frame=pl.DataFrame(),
            findings=tuple(findings),
            source_file=str(path),
            skipped=True,
            skip_reason=message,
            failed=True,
        )
    return IngestedInput(
        role=role,
        frame=mapped.frame,
        findings=tuple(findings),
        source_file=str(path),
        skipped=False,
    )


def _read_error_finding(error: ReadError, source_file: str) -> Finding:
    spec = _READ_ERROR_RULES.get(error.rule_id, ING_001)
    message = error.message + (f" ({error.hint})" if error.hint else "")
    return Finding.from_spec(spec, message, source_file=source_file)
