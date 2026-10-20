"""Resolve and load inputs for an engine run.

Accepts either file paths (read through the ingestion stack) or in-memory
Polars/pandas DataFrames (which skip file I/O but still run canonical mapping).
Optional-role failures are recorded as findings; required-role failures raise
:class:`~rosterops.exceptions.InputError`.

Caller-owned DataFrames are never mutated: pandas inputs are copied; Polars
inputs are copied before mapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from rosterops.config import InputRoleConfig, RosterConfig
from rosterops.exceptions import InputError
from rosterops.interop import is_pandas_dataframe, to_polars
from rosterops.io.ingest import IngestedInput
from rosterops.io.raw import RawTable, ReadError
from rosterops.mapping.canonical import map_to_canonical
from rosterops.rules.base import Finding

__all__ = ["LoadedInputs", "SourceSpec", "load_inputs"]

#: A role source is either a filesystem path or an in-memory DataFrame.
SourceSpec = str | Path | pl.DataFrame | Any


@dataclass(slots=True)
class LoadedInputs:
    """Canonical frames and findings for all loaded roles."""

    frames: dict[str, pl.DataFrame]
    findings: list[Finding]
    ingested: dict[str, IngestedInput]
    input_files: list[dict[str, object]]


def load_inputs(
    config: RosterConfig,
    sources: dict[str, SourceSpec],
) -> LoadedInputs:
    """Load every configured/provided role into canonical frames.

    ``sources`` overrides/augments the role paths in ``config.inputs`` (CLI
    flags and API arguments land here). A role present in neither is skipped.
    """
    frames: dict[str, pl.DataFrame] = {}
    findings: list[Finding] = []
    ingested: dict[str, IngestedInput] = {}
    input_files: list[dict[str, object]] = []

    roles = sorted(set(config.inputs) | set(sources))
    for role in roles:
        source = sources.get(role)
        cfg = config.inputs.get(role, InputRoleConfig(required=role == "baseline"))
        if source is None:
            if cfg.path is None:
                continue
            source = cfg.path

        result = _load_role(role, source, cfg, config)
        ingested[role] = result
        findings.extend(result.findings)
        if not result.skipped and result.frame.height >= 0 and result.frame.columns:
            frames[role] = result.frame
        if result.source_file:
            input_files.append(
                {
                    "role": role,
                    "name": Path(result.source_file).name,
                    "path": result.source_file,
                }
            )
    return LoadedInputs(
        frames=frames, findings=findings, ingested=ingested, input_files=input_files
    )


def _load_role(
    role: str,
    source: SourceSpec,
    cfg: InputRoleConfig,
    config: RosterConfig,
) -> IngestedInput:
    if is_pandas_dataframe(source):
        try:
            frame = to_polars(source)
        except Exception as exc:
            raise InputError(str(exc)) from exc
        return _map_frame(role, frame, cfg, source_file=f"<{role}:pandas>")
    if isinstance(source, pl.DataFrame):
        return _map_frame(role, source.clone(), cfg, source_file=f"<{role}:polars>")
    # Path-like -> file read.
    path = Path(source)
    read_cfg = cfg.model_copy(update={"path": str(path)})
    from rosterops.io.ingest import ingest_role

    return ingest_role(role, read_cfg)


def _map_frame(
    role: str,
    frame: pl.DataFrame,
    cfg: InputRoleConfig,
    *,
    source_file: str,
) -> IngestedInput:
    table = RawTable(
        frame=frame,
        source_file=source_file,
        source_sheet=None,
        header_row=0,
        first_data_row=1,
        format="dataframe",
        source_columns=tuple(frame.columns),
    )
    mapped = map_to_canonical(
        role,
        table,
        cfg,
        source_file=source_file,
        source_sheet=None,
        first_data_row=1,
    )
    findings = tuple(mapped.findings)
    if mapped.failed:
        message = f"input role {role!r} could not be mapped: see findings"
        if cfg.required:
            raise InputError(message)
        return IngestedInput(
            role=role,
            frame=pl.DataFrame(),
            findings=findings,
            source_file=source_file,
            skipped=True,
            skip_reason=message,
            failed=True,
        )
    return IngestedInput(role=role, frame=mapped.frame, findings=findings, source_file=source_file)


def _read_error_finding(error: ReadError, source_file: str) -> Finding:
    from rosterops.rules.input_rules import ING_001, ING_002, ING_003

    spec = {"ING-001": ING_001, "ING-002": ING_002, "ING-003": ING_003}.get(error.rule_id, ING_001)
    message = error.message + (f" ({error.hint})" if error.hint else "")
    return Finding.from_spec(spec, message, source_file=source_file)
