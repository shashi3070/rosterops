"""Input reading, format detection, and source-to-canonical mapping.

This package turns arbitrary supported files (CSV, Parquet, Excel) into
canonical Polars frames with lineage attached. It never silently drops rows:
every structural or parse failure becomes an ``ING-*``/``SCH-*`` finding that
carries file/sheet/row/column context.
"""

from __future__ import annotations

from rosterops.io.ingest import IngestedInput, ingest_role
from rosterops.io.raw import RawTable, ReadError, ReadResult
from rosterops.io.readers import SUPPORTED_FORMATS, detect_format, read_raw

__all__ = [
    "SUPPORTED_FORMATS",
    "IngestedInput",
    "RawTable",
    "ReadError",
    "ReadResult",
    "detect_format",
    "ingest_role",
    "read_raw",
]
