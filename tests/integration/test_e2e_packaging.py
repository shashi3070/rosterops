"""End-to-end packaging test (REQUIREMENTS §16/§17, Phase 8).

Builds a wheel, installs it into a throwaway virtual environment, and runs the
console entry point against the shipped examples **from outside the source
checkout** (working directory is a temp dir). This proves the package works when
installed, not just from the checkout.

Skipped by default because it is slow and needs network access to create the
venv. Enable with ``ROSTEROPS_E2E=1``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("ROSTEROPS_E2E") != "1",
    reason="set ROSTEROPS_E2E=1 to run the slow packaging end-to-end test",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_wheel_install_and_cli_outside_checkout(tmp_path: Path) -> None:
    repo = _repo_root()
    dist = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist)],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    wheels = list(dist.glob("rosterops-*.whl"))
    assert wheels, "wheel was not built"

    env_dir = tmp_path / "venv"
    venv.create(env_dir, with_pip=True, clear=True)
    py = env_dir / ("Scripts" if os.name == "nt" else "bin") / "python"
    subprocess.run(
        [str(py), "-m", "pip", "install", "--quiet", str(wheels[0])],
        check=True,
        capture_output=True,
    )

    # Run from a directory that is not the checkout.
    work = tmp_path / "work"
    work.mkdir()
    examples = repo / "examples"
    out = work / "out"
    proc = subprocess.run(
        [
            str(py),
            "-m",
            "rosterops.cli",
            "process",
            "--config",
            str(examples / "config" / "scenario.yaml"),
            "--baseline",
            str(examples / "inputs" / "baseline.csv"),
            "--baseline-date",
            "2026-09-30",
            "--as-of",
            "2026-10-31",
            "--transfers",
            str(examples / "inputs" / "transfers.csv"),
            "--promotions",
            str(examples / "inputs" / "promotions.csv"),
            "--leaves",
            str(examples / "inputs" / "leaves.csv"),
            "--returns",
            str(examples / "inputs" / "returns.csv"),
            "--terminations",
            str(examples / "inputs" / "terminations.csv"),
            "--territories",
            str(examples / "inputs" / "territories.csv"),
            "--output-dir",
            str(out),
            "--overwrite",
        ],
        cwd=work,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    assert (out / "final_roster.csv").exists()
    assert (out / "reconciliation.json").exists()
    assert (out / "run_metadata.json").exists()
