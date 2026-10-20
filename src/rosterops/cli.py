"""Command-line interface for rosterops.

Exit codes (REQUIREMENTS §13): 0 = success, 1 = completed with error-severity
findings or reconciliation failures, 2 = the run could not be performed
(invalid configuration, unreadable required input, impossible reconstruction,
or a command not yet available).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from rosterops.config import RosterConfig
from rosterops.exceptions import ConfigError
from rosterops.rules import all_rules, get_rule
from rosterops.version import __version__

__all__ = ["build_parser", "main"]


def _configure_std_streams() -> None:
    """Force UTF-8 stdio so rule names (§8) render regardless of console codepage.

    Windows consoles default to a legacy codepage (cp1252) that cannot encode
    characters such as ``≥``, ``≠``, or the minus sign used verbatim in the rule
    catalogue. Reconfiguring the streams keeps output identical across locales.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    """Build the full command-line parser (subcommands per REQUIREMENTS §13)."""
    parser = argparse.ArgumentParser(
        prog="rosterops",
        description=(
            "Deterministic roster processing and validation for pharma commercial operations."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"rosterops {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command")

    process = subparsers.add_parser(
        "process",
        help="Reconstruct the roster as of a date from a baseline and event files",
    )
    process.add_argument("--baseline", required=True, help="Baseline roster file")
    process.add_argument(
        "--baseline-date", required=True, help="Baseline snapshot date (YYYY-MM-DD)"
    )
    process.add_argument("--as-of", required=True, help="Reconstruction date (YYYY-MM-DD)")
    process.add_argument("--transfers", help="Transfer events file")
    process.add_argument("--promotions", help="Promotion events file")
    process.add_argument("--terminations", help="Termination events file")
    process.add_argument("--leaves", help="Leave-of-absence events file")
    process.add_argument("--returns", help="Return-from-leave events file")
    process.add_argument("--hires", help="New-hire events file")
    process.add_argument("--rehires", help="Rehire events file")
    process.add_argument("--coverage", help="Temporary coverage events file")
    process.add_argument("--territories", help="Territory master file")
    process.add_argument("--managers", help="Manager master file")
    process.add_argument("--config", required=True, help="Configuration YAML file")
    process.add_argument("--output-dir", required=True, help="Directory for reports")
    process.add_argument(
        "--overwrite", action="store_true", help="Allow overwriting the output dir"
    )
    process.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit 1 when any warning-severity finding exists",
    )

    validate = subparsers.add_parser(
        "validate",
        help="Validate a single consolidated roster snapshot",
    )
    validate.add_argument("--snapshot", required=True, help="Consolidated roster file")
    validate.add_argument("--as-of", required=True, help="Effective date (YYYY-MM-DD)")
    validate.add_argument("--territories", help="Territory master file")
    validate.add_argument("--config", required=True, help="Configuration YAML file")
    validate.add_argument("--output-dir", required=True, help="Directory for reports")
    validate.add_argument(
        "--overwrite", action="store_true", help="Allow overwriting the output dir"
    )
    validate.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit 1 when any warning-severity finding exists",
    )

    validate_inputs = subparsers.add_parser(
        "validate-inputs",
        help="Validate configuration and inputs without reconstructing",
    )
    validate_inputs.add_argument("--config", required=True, help="Configuration YAML file")

    rules = subparsers.add_parser("rules", help="Inspect validation rules")
    rules_sub = rules.add_subparsers(dest="rules_command")
    rules_sub.add_parser("list", help="List all rules")
    describe = rules_sub.add_parser("describe", help="Describe one rule")
    describe.add_argument("rule_id", help="Rule ID, e.g. TRF-002")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning the documented process exit code."""
    _configure_std_streams()
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "rules":
        return _rules_command(args)
    if args.command == "validate-inputs":
        return _validate_inputs_command(args)
    if args.command == "process":
        return _process_command(args)
    if args.command == "validate":
        return _validate_command(args)
    parser.error(f"unknown command: {args.command}")
    return 2


_EVENT_FLAGS = (
    ("transfers", "transfers"),
    ("promotions", "promotions"),
    ("terminations", "terminations"),
    ("leaves", "leaves"),
    ("returns", "returns"),
    ("hires", "hires"),
    ("rehires", "rehires"),
    ("coverage", "coverage"),
)

_MASTER_FLAGS = (("territories", "territories"), ("managers", "managers"))


def _load_config(args: argparse.Namespace) -> RosterConfig | None:
    try:
        return RosterConfig.from_file(args.config)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return None


def _process_command(args: argparse.Namespace) -> int:
    from rosterops.engine.api import RosterEngine
    from rosterops.exceptions import RosterOpsError
    from rosterops.outputs import console_report, write_outputs

    config = _load_config(args)
    if config is None:
        return 2

    sources: dict[str, str] = {"baseline": args.baseline}
    for attr, role in (*_EVENT_FLAGS, *_MASTER_FLAGS):
        value = getattr(args, attr, None)
        if value:
            sources[role] = value

    try:
        result = RosterEngine(config).process(
            **sources,  # type: ignore[arg-type]
            baseline_date=args.baseline_date,
            as_of=args.as_of,
        )
    except RosterOpsError as exc:
        print(f"run failed: {exc}", file=sys.stderr)
        return 2

    try:
        report = write_outputs(
            result,
            args.output_dir,
            input_paths=[p for p in sources.values() if isinstance(p, str)],
            overwrite=args.overwrite,
        )
    except RosterOpsError as exc:
        print(f"output error: {exc}", file=sys.stderr)
        return 2

    print(console_report(result, report))
    return result.exit_code(fail_on_warning=args.fail_on_warning)


def _validate_command(args: argparse.Namespace) -> int:
    from rosterops.engine.api import RosterEngine
    from rosterops.exceptions import RosterOpsError
    from rosterops.outputs import console_report, write_outputs

    config = _load_config(args)
    if config is None:
        return 2

    sources: dict[str, str] = {"snapshot": args.snapshot}
    if getattr(args, "territories", None):
        sources["territories"] = args.territories

    try:
        result = RosterEngine(config).validate_snapshot(
            **sources,  # type: ignore[arg-type]
            as_of=args.as_of,
        )
    except RosterOpsError as exc:
        print(f"run failed: {exc}", file=sys.stderr)
        return 2

    try:
        report = write_outputs(
            result,
            args.output_dir,
            input_paths=[p for p in sources.values() if isinstance(p, str)],
            overwrite=args.overwrite,
        )
    except RosterOpsError as exc:
        print(f"output error: {exc}", file=sys.stderr)
        return 2

    print(console_report(result, report))
    return result.exit_code(fail_on_warning=args.fail_on_warning)


def _rules_command(args: argparse.Namespace) -> int:
    if args.rules_command == "describe":
        try:
            spec = get_rule(args.rule_id)
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"{spec.id} — {spec.name}")
        print(f"  group:          {spec.group}")
        print(f"  default severity: {spec.default_severity.label}")
        print(f"  modes:          {', '.join(spec.mode_labels)}")
        if spec.params:
            declared = ", ".join(f"{k}: {t.__name__}" for k, t in sorted(spec.params.items()))
            print(f"  parameters:     {declared}")
        else:
            print("  parameters:     none")
        print(f"  description:    {spec.description}")
        return 0

    # Default: list (also covers `rules` with no subcommand).
    print(f"{'ID':<10} {'GROUP':<15} {'SEVERITY':<9} {'MODES':<18} NAME")
    for spec in all_rules():
        print(
            f"{spec.id:<10} {spec.group:<15} {spec.default_severity.label:<9} "
            f"{','.join(spec.mode_labels):<18} {spec.name}"
        )
    print(f"\n{len(all_rules())} rules")
    return 0


def _validate_inputs_command(args: argparse.Namespace) -> int:
    try:
        config = RosterConfig.from_file(args.config)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    print(f"configuration OK: {args.config}")
    print(f"  version: {config.version}")
    print(f"  grain:   {config.data.grain.value}")
    print(f"  inputs:  {len(config.inputs)} role(s) configured")
    print(f"  rules:   {len(config.rules)} override(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
