"""Rule package: importing it registers every rule specification."""

from __future__ import annotations

from rosterops.rules import (
    coverage_rules,
    employment_rules,
    grain_rules,
    hierarchy_rules,
    identifier_rules,
    input_rules,
    leave_rules,
    promotion_rules,
    reconciliation_rules,
    temporal_rules,
    territory_rules,
    transfer_rules,
)
from rosterops.rules.base import (
    Finding,
    RuleSpec,
    all_rule_ids,
    all_rules,
    get_rule,
    has_rule,
    severity_rank,
    sort_and_number,
    sort_findings,
)

__all__ = [
    "Finding",
    "RuleSpec",
    "all_rule_ids",
    "all_rules",
    "coverage_rules",
    "employment_rules",
    "get_rule",
    "grain_rules",
    "has_rule",
    "hierarchy_rules",
    "identifier_rules",
    "input_rules",
    "leave_rules",
    "promotion_rules",
    "reconciliation_rules",
    "severity_rank",
    "sort_and_number",
    "sort_findings",
    "temporal_rules",
    "territory_rules",
    "transfer_rules",
]
