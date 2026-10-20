from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Repository root (contains REQUIREMENTS.md and examples/)."""
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def example_config_path(repo_root: Path) -> Path:
    """Path to the shipped illustrative configuration profile."""
    return repo_root / "examples" / "config" / "generic_pharma.yaml"
