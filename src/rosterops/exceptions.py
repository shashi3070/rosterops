"""Error hierarchy for rosterops.

Business-invalid-but-processable data must surface as validation findings,
not exceptions. Exceptions are reserved for failures that prevent a run:
bad configuration, unreadable inputs, impossible reconstruction.
"""

from __future__ import annotations


class RosterOpsError(Exception):
    """Base class for all rosterops errors."""


class ConfigError(RosterOpsError):
    """Configuration is invalid, unreadable, or unsafe."""


class InputError(RosterOpsError):
    """An input source is missing, unreadable, or structurally unusable."""


class ReconstructionError(RosterOpsError):
    """The requested roster state cannot be reconstructed from the given inputs."""
