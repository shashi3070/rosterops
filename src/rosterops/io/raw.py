"""Raw loaded-table structures and read errors.

A :class:`RawTable` is the result of reading one file/sheet before any
canonical mapping: a Polars frame of source columns plus the lineage context
needed to locate every cell (file, sheet, header row, first data row).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

__all__ = ["RawTable", "ReadError", "ReadResult"]


class ReadError(Exception):
    """A structural read failure carrying the rule context for reporting.

    ``rule_id`` is one of ``ING-001``/``ING-002``/``ING-003``; the caller turns
    it into a :class:`~rosterops.rules.base.Finding` (or an ``InputError`` for
    required roles) instead of letting a raw library exception escape.
    """

    def __init__(self, rule_id: str, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.rule_id = rule_id
        self.message = message
        self.hint = hint


@dataclass(frozen=True, slots=True)
class RawTable:
    """A loaded source table prior to canonical mapping."""

    frame: pl.DataFrame
    source_file: str
    source_sheet: str | None
    #: 0-based row index in the file where the header row sits.
    header_row: int
    #: 1-based spreadsheet/CSV line number of the first data row.
    first_data_row: int
    format: str
    #: Source column names in original file order.
    source_columns: tuple[str, ...] = ()

    @property
    def height(self) -> int:
        return self.frame.height

    @property
    def path(self) -> Path:
        return Path(self.source_file)

    def row_number(self, row_index: int) -> int:
        """Map a 0-based frame row index to the 1-based source data row number."""
        return self.first_data_row + row_index


@dataclass(frozen=True, slots=True)
class ReadResult:
    """Outcome of :func:`~rosterops.io.readers.read_raw` for one input role."""

    table: RawTable | None
    errors: tuple[ReadError, ...] = field(default_factory=tuple)
    #: True when the governing failure is "not found" and the role is optional.
    skipped: bool = False
