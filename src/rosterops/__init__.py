"""rosterops — deterministic, configurable pharma roster processing and validation."""

from __future__ import annotations

from rosterops.config import RosterConfig
from rosterops.exceptions import ConfigError, InputError, ReconstructionError, RosterOpsError
from rosterops.interop import is_pandas_dataframe, to_pandas, to_polars
from rosterops.version import __version__

__all__ = [
    "ConfigError",
    "InputError",
    "ReconstructionError",
    "RosterConfig",
    "RosterOpsError",
    "__version__",
    "is_pandas_dataframe",
    "to_pandas",
    "to_polars",
]
