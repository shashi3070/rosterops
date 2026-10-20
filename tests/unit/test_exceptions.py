from __future__ import annotations

from rosterops.exceptions import ConfigError, InputError, ReconstructionError, RosterOpsError


def test_hierarchy() -> None:
    assert issubclass(ConfigError, RosterOpsError)
    assert issubclass(InputError, RosterOpsError)
    assert issubclass(ReconstructionError, RosterOpsError)
    assert issubclass(RosterOpsError, Exception)


def test_message_roundtrip() -> None:
    err = ConfigError("bad field: version")
    assert str(err) == "bad field: version"
