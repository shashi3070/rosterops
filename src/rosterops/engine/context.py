"""Execution context shared by rule implementations.

Holds the resolved configuration, effective rule settings, the canonical frames
for each loaded role, the reconstructed baseline state, and the accumulated
findings. Rule implementations read from this and append findings; the engine
collects and deterministically orders them at the end.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import polars as pl

from rosterops.config import RosterConfig
from rosterops.engine.state import BaselineState
from rosterops.models import Grain
from rosterops.rules.base import Finding
from rosterops.rules.settings import RuleSetting, resolve_settings

__all__ = ["EngineContext"]


@dataclass(slots=True)
class EngineContext:
    """Mutable rule-execution context for one run."""

    config: RosterConfig
    mode: str
    as_of: date | None = None
    baseline_date: date | None = None
    frames: dict[str, pl.DataFrame] = field(default_factory=dict)
    state: BaselineState = field(default_factory=BaselineState)
    findings: list[Finding] = field(default_factory=list)
    settings: dict[str, RuleSetting] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.settings:
            self.settings = resolve_settings(self.config)

    # -- convenience accessors --------------------------------------------
    @property
    def grain(self) -> Grain:
        return self.config.data.grain

    def frame(self, role: str) -> pl.DataFrame | None:
        return self.frames.get(role)

    def has(self, role: str) -> bool:
        return role in self.frames

    def setting(self, rule_id: str) -> RuleSetting:
        return self.settings[rule_id]

    def enabled(self, rule_id: str) -> bool:
        return self.settings[rule_id].enabled

    def severity_of(self, rule_id: str) -> object:
        return self.settings[rule_id].severity

    def param(self, rule_id: str, name: str, default: object = None) -> object:
        return self.settings[rule_id].params.get(name, default)

    def emit(
        self,
        spec: Any,
        message: str,
        *,
        severity_override: bool = True,
        **fields: Any,
    ) -> None:
        """Append a finding using the rule's effective severity.

        Disabled rules are skipped. The spec is a :class:`RuleSpec`.
        """
        rule_id = spec.id
        setting = self.settings.get(rule_id)
        if setting is not None and not setting.enabled:
            return
        severity = setting.severity if setting is not None else None
        finding = Finding.from_spec(
            spec,
            message,
            severity=severity if severity_override else None,
            **fields,
        )
        self.findings.append(finding)
