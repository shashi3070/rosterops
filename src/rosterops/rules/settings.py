"""Resolve effective per-rule settings from configuration overrides.

A rule's *effective* behavior is its spec defaults adjusted by any
``rules:`` override in the configuration (enable/disable, severity, params).
Structural rules (input/schema/grain) may have severity changed but never
disabled silently — see ``STRUCTURAL_GROUPS``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rosterops.config import RosterConfig
from rosterops.models import Severity
from rosterops.rules.base import RuleSpec, all_rules, get_rule

__all__ = ["STRUCTURAL_GROUPS", "RuleSetting", "resolve_settings"]

#: Groups whose rules may not be silently disabled (structural integrity).
STRUCTURAL_GROUPS: frozenset[str] = frozenset({"input", "grain"})


@dataclass(frozen=True, slots=True)
class RuleSetting:
    """Effective settings for one rule after applying config overrides."""

    spec: RuleSpec
    enabled: bool
    severity: Severity
    params: dict[str, object] = field(default_factory=dict)


def resolve_settings(config: RosterConfig) -> dict[str, RuleSetting]:
    """Return effective settings for every registered rule.

    Overrides are validated at config load: unknown IDs already raise there.
    A structural rule (input/grain group) cannot be disabled — attempts are
    ignored so schema/cardinality violations can never be silently hidden; its
    severity *may* still be overridden.
    """
    overrides = {override.id: override for override in config.rules}
    settings: dict[str, RuleSetting] = {}
    for spec in all_rules():
        override = overrides.get(spec.id)
        enabled = True
        severity = spec.default_severity
        params: dict[str, object] = {}
        if override is not None:
            enabled = override.enabled
            if override.severity is not None:
                severity = override.severity
            params = dict(override.params)
        if spec.group in STRUCTURAL_GROUPS:
            enabled = True
        settings[spec.id] = RuleSetting(
            spec=spec, enabled=enabled, severity=severity, params=params
        )
    return settings


def effective_setting(settings: dict[str, RuleSetting], rule_id: str) -> RuleSetting:
    """Look up a rule's effective setting, falling back to spec defaults."""
    if rule_id in settings:
        return settings[rule_id]
    spec = get_rule(rule_id)
    return RuleSetting(spec=spec, enabled=True, severity=spec.default_severity)
