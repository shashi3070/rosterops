"""Format detection and raw table readers.

CSV and Parquet are always available through Polars. Excel requires the
``rosterops[excel]`` extra (``fastexcel`` for reads via Polars, ``openpyxl``
for report writes); its absence yields an actionable ``ING-002`` message rather
than a raw ``ImportError``.

All string-like columns are read as ``pl.String`` (no schema inference) so that
significant leading zeros in identifiers survive end-to-end. Typed conversion
happens later, in the mapping layer, where failures become located findings.
"""

from __future__ import annotations

import re
from pathlib import Path

import polars as pl

from rosterops.io.raw import RawTable, ReadError

__all__ = ["SUPPORTED_FORMATS", "detect_format", "read_raw"]

_DUPLICATED_SUFFIX = re.compile(r"_duplicated_\d+$")

#: Extension (lowercase, no dot) -> canonical format name.
SUPPORTED_FORMATS: dict[str, str] = {
    "csv": "csv",
    "txt": "csv",
    "parquet": "parquet",
    "pq": "parquet",
    "xlsx": "excel",
    "xls": "excel",
    "xlsm": "excel",
    "xlsb": "excel",
}

_EXCEL_EXTENSIONS = frozenset({"xlsx", "xls", "xlsm", "xlsb"})

_EXCEL_INSTALL_HINT = (
    "Excel support requires the optional dependency: install with "
    "`pip install rosterops[excel]` (provides fastexcel for reading and "
    "openpyxl for writing)."
)


def detect_format(path: Path, declared: str | None = None) -> str:
    """Resolve the input format from an explicit declaration or the extension.

    Raises :class:`ReadError` (``ING-002``) when the extension is unknown.
    """
    if declared is not None:
        if declared not in {"csv", "parquet", "excel"}:
            raise ReadError(
                "ING-002",
                f"unsupported declared format {declared!r}",
                hint=f"supported formats: {', '.join(sorted(set(SUPPORTED_FORMATS.values())))}",
            )
        return declared
    suffix = path.suffix.lower().lstrip(".")
    fmt = SUPPORTED_FORMATS.get(suffix)
    if fmt is None:
        supported = ", ".join(sorted(set(SUPPORTED_FORMATS.values())))
        raise ReadError(
            "ING-002",
            f"unsupported file extension {path.suffix!r} for {path.name!r}",
            hint=f"supported formats: {supported}",
        )
    return fmt


def read_raw(
    path: Path,
    *,
    format: str | None = None,
    sheet_name: str | None = None,
    header_row: int = 0,
) -> RawTable:
    """Read one input source into a :class:`RawTable` (all columns as strings).

    ``header_row`` is the 0-based row index containing column headers within the
    sheet/file; data begins on the following row.
    """
    if not path.exists():
        raise ReadError("ING-001", f"input file not found: {path}")
    if not path.is_file():
        raise ReadError("ING-001", f"input path is not a file: {path}")

    fmt = detect_format(path, format)
    try:
        if fmt == "csv":
            frame = _read_csv(path, header_row)
            sheet = None
            first_data_row = header_row + 2
        elif fmt == "parquet":
            frame = _read_parquet(path)
            sheet = None
            first_data_row = header_row + 2
        else:
            frame, sheet, first_data_row = _read_excel(path, sheet_name, header_row)
    except ReadError:
        raise
    except PermissionError as exc:
        raise ReadError("ING-001", f"input file is not readable: {path}: {exc}") from exc
    except OSError as exc:
        raise ReadError("ING-001", f"input file could not be read: {path}: {exc}") from exc

    # Normalize duplicate/blank headers deterministically (blank -> column_N).
    frame = _normalize_headers(frame)
    return RawTable(
        frame=frame,
        source_file=str(path),
        source_sheet=sheet,
        header_row=header_row,
        first_data_row=first_data_row,
        format=fmt,
        source_columns=tuple(frame.columns),
    )


def _read_csv(path: Path, header_row: int) -> pl.DataFrame:
    try:
        return pl.read_csv(
            path,
            infer_schema=False,
            null_values=[],
            empty_string_is_null=False,
            skip_rows=header_row,
            has_header=True,
            encoding="utf8-lossy",
        )
    except (pl.exceptions.PolarsError, UnicodeDecodeError) as exc:
        raise ReadError("ING-002", f"CSV file could not be parsed: {path}: {exc}") from exc


def _read_parquet(path: Path) -> pl.DataFrame:
    try:
        frame = pl.read_parquet(path)
    except (pl.exceptions.PolarsError, OSError) as exc:
        raise ReadError("ING-002", f"Parquet file could not be parsed: {path}: {exc}") from exc
    # Cast every column to string so downstream mapping is uniform; values keep
    # their exact integer/boolean representation (leading zeros are a source
    # concern for text formats, but casting avoids surprises for numeric IDs).
    return frame.with_columns(pl.all().cast(pl.String, strict=False))


def _read_excel(
    path: Path, sheet_name: str | None, header_row: int
) -> tuple[pl.DataFrame, str, int]:
    sheets = _excel_sheet_names(path)

    if not sheets:
        raise ReadError("ING-003", f"Excel workbook has no worksheets: {path}")

    if sheet_name is None:
        sheet = sheets[0]
    else:
        if sheet_name not in sheets:
            raise ReadError(
                "ING-003",
                f"worksheet {sheet_name!r} not found in {path.name!r}; "
                f"available: {', '.join(sheets)}",
            )
        sheet = sheet_name

    try:
        frame = pl.read_excel(
            path,
            sheet_name=sheet,
            engine="calamine",
            read_options={"header_row": header_row},
            infer_schema_length=0,
        )
    except (pl.exceptions.PolarsError, OSError) as exc:
        raise ReadError("ING-003", f"worksheet {sheet!r} could not be read: {path}: {exc}") from exc
    frame = frame.with_columns(pl.all().cast(pl.String, strict=False))
    return frame, sheet, header_row + 2


def _excel_sheet_names(path: Path) -> list[str]:
    try:
        import fastexcel
    except ImportError as exc:
        raise ReadError("ING-002", _EXCEL_INSTALL_HINT) from exc
    try:
        reader = fastexcel.read_excel(str(path))
        return list(reader.sheet_names)
    except Exception as exc:
        raise ReadError("ING-002", f"Excel workbook could not be opened: {path}: {exc}") from exc


def _normalize_headers(frame: pl.DataFrame) -> pl.DataFrame:
    """Make header names unique and non-empty while preserving file order.

    Polars already appends ``_duplicated_N`` for repeated headers; we strip that
    suffix first so our renaming scheme (``name_2``, ``name_3``, ...) is applied
    uniformly, and we replace blank headers with ``column_N`` (1-based).
    """
    seen: dict[str, int] = {}
    new_columns: list[str] = []
    for index, name in enumerate(frame.columns):
        base = (name or "").strip()
        base = _DUPLICATED_SUFFIX.sub("", base) or base
        if not base:
            base = f"column_{index + 1}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        new_columns.append(base if count == 0 else f"{base}_{count + 1}")
    if new_columns != list(frame.columns):
        frame = frame.rename(dict(zip(frame.columns, new_columns, strict=True)))
    return frame
