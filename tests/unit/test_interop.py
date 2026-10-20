from __future__ import annotations

import importlib.util

import polars as pl
import pytest

from rosterops.exceptions import InputError
from rosterops.interop import PANDAS_INSTALL_HINT, is_pandas_dataframe, to_pandas, to_polars

_HAS_PANDAS = importlib.util.find_spec("pandas") is not None

pytestmark = pytest.mark.skipif(not _HAS_PANDAS, reason="rosterops[pandas] extra not installed")


def test_is_pandas_dataframe_detection() -> None:
    import pandas as pd

    assert is_pandas_dataframe(pd.DataFrame({"a": [1]}))
    assert not is_pandas_dataframe(pl.DataFrame({"a": [1]}))
    assert not is_pandas_dataframe([1, 2, 3])
    assert not is_pandas_dataframe("nope")


def test_to_polars_from_pandas() -> None:
    import pandas as pd

    frame = pd.DataFrame({"employee_id": ["007", "123"], "territory_id": ["T1", "T2"]})
    result = to_polars(frame)
    assert isinstance(result, pl.DataFrame)
    assert result["employee_id"].to_list() == ["007", "123"]


def test_to_polars_does_not_mutate_caller() -> None:
    import pandas as pd

    frame = pd.DataFrame({"employee_id": ["007"]})
    original = frame.copy(deep=True)
    result = to_polars(frame)
    result = result.with_columns(pl.lit("changed").alias("employee_id"))
    # Caller's frame is untouched.
    assert frame.equals(original)
    assert frame["employee_id"].to_list() == ["007"]


def test_to_polars_passthrough_polars() -> None:
    frame = pl.DataFrame({"a": [1]})
    result = to_polars(frame)
    assert result is not frame  # cloned
    assert result.equals(frame)
    assert to_polars(frame, copy=False) is frame


def test_to_polars_rejects_unsupported_type() -> None:
    with pytest.raises(InputError, match="expected a pandas or Polars DataFrame"):
        to_polars([1, 2, 3])


def test_to_polars_without_pandas_reports_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "pandas":
            raise ImportError("no pandas")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert not is_pandas_dataframe(object())
    with pytest.raises(InputError, match="expected a pandas or Polars DataFrame"):
        to_polars(object())


def test_to_pandas_roundtrip() -> None:
    import pandas as pd

    frame = pl.DataFrame({"employee_id": ["007"], "is_primary": [True]})
    result = to_pandas(frame)
    assert isinstance(result, pd.DataFrame)
    assert result["employee_id"].tolist() == ["007"]


def test_install_hint_mentions_extra() -> None:
    assert "rosterops[pandas]" in PANDAS_INSTALL_HINT
