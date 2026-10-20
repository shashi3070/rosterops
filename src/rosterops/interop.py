"""Optional pandas <-> Polars interoperability (decision D11).

The engine's internals are Polars. This module is the *only* place pandas is
touched: it converts caller-supplied ``pandas.DataFrame`` objects into Polars
frames for processing and can convert results back to pandas on request.

pandas is an optional dependency (``rosterops[pandas]``). When it is absent,
pandas operations raise :class:`~rosterops.exceptions.InputError` with an
actionable install hint rather than a raw ``ImportError``. Conversions always
copy — the caller's frame is never mutated.
"""

from __future__ import annotations

from typing import Any, cast

import polars as pl

from rosterops.exceptions import InputError

__all__ = ["PANDAS_INSTALL_HINT", "is_pandas_dataframe", "to_pandas", "to_polars"]

PANDAS_INSTALL_HINT = (
    "pandas support requires the optional dependency: install with `pip install rosterops[pandas]`."
)


def is_pandas_dataframe(value: object) -> bool:
    """True when ``value`` is a pandas ``DataFrame`` (import-safe if pandas absent)."""
    try:
        import pandas as pd
    except ImportError:
        return False
    return isinstance(value, pd.DataFrame)


def to_polars(frame: object, *, copy: bool = True) -> pl.DataFrame:
    """Convert a pandas ``DataFrame`` to Polars without mutating the caller's frame.

    Non-pandas values pass through unchanged when they are already Polars frames.
    Raises :class:`InputError` for unsupported types or when pandas is missing.
    """
    if isinstance(frame, pl.DataFrame):
        return frame.clone() if copy else frame
    if not is_pandas_dataframe(frame):
        raise InputError(f"expected a pandas or Polars DataFrame, got {type(frame).__name__}")
    # ``frame`` is a pandas DataFrame here (guaranteed by is_pandas_dataframe).
    working = cast("Any", frame)
    if copy:
        working = working.copy(deep=True)
    return pl.from_pandas(working, include_index=False)


def to_pandas(frame: pl.DataFrame) -> Any:
    """Convert a Polars frame to pandas, raising ``InputError`` without the extra."""
    try:
        import pandas as pd  # noqa: F401
    except ImportError as exc:
        raise InputError(PANDAS_INSTALL_HINT) from exc
    try:
        return frame.to_pandas()
    except ModuleNotFoundError as exc:  # pyarrow is required by Polars' converter
        raise InputError(
            f"{PANDAS_INSTALL_HINT} (converting to pandas also needs pyarrow: "
            "`pip install pyarrow`)"
        ) from exc
