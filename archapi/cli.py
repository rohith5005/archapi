from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from archapi.core import ArchAPI


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, default=str))


def cmd_detect(args: argparse.Namespace) -> int:
    api = ArchAPI(args.path)
    result = api.detect_framework()
    _print_json({
        "framework": result.framework,
        "confidence": result.confidence,
        "reasons": result.reasons,
    })
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    api = ArchAPI(args.path)
    api.detect_framework()
    scan = api.scan()
    _print_json({
        "framework": scan.framework,
        "routes": len(scan.routes),
        "controllers": len(scan.controllers),
        "services": len(scan.services),
        "models": len(scan.models),
        "schemas": len(scan.schemas),
        "middleware": len(scan.middleware),
        "tests": len(scan.tests),
        "config_files": len(scan.config_files),
    })
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    api = ArchAPI(args.path)
    plan = api.plan_api(args.request)
    _print_json({
        "method": plan.method,
        "path": plan.path,
        "entities": plan.entities,
        "layers": plan.layers,
        "generation_allowed": plan.generation_allowed,
        "reason": plan.reason,
    })
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    api = ArchAPI(args.path)
    dry_run = not args.apply

    result = api.generate_api(args.request, dry_run=dry_run)

    if not result.validation_report.success:
        print("Generation failed:", file=sys.stderr)
        for err in result.validation_report.errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    if result.warnings:
        for w in result.warnings:
            print(f"warning: {w}", file=sys.stderr)

    for f in result.files:
        status = "applied" if not dry_run else "dry-run"
        print(f"[{status}] {f.path}")

    if dry_run and result.files:
        print("\nRun with --apply to write files.")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="archapi",
        description="Architecture-preserving REST API synthesis",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    detect_p = sub.add_parser("detect", help="Detect the framework of a project")
    detect_p.add_argument("path", nargs="?", default=".", help="Project path (default: .)")
    detect_p.set_defaults(func=cmd_detect)

    scan_p = sub.add_parser("scan", help="Scan project structure")
    scan_p.add_argument("path", nargs="?", default=".", help="Project path (default: .)")
    scan_p.set_defaults(func=cmd_scan)

    plan_p = sub.add_parser("plan", help="Plan an API without generating code")
    plan_p.add_argument("path", nargs="?", default=".", help="Project path (default: .)")
    plan_p.add_argument("request", help="Natural-language API request, e.g. 'add a POST /users endpoint'")
    plan_p.set_defaults(func=cmd_plan)

    gen_p = sub.add_parser("generate", help="Generate API code (dry-run by default)")
    gen_p.add_argument("path", nargs="?", default=".", help="Project path (default: .)")
    gen_p.add_argument("request", help="Natural-language API request")
    gen_p.add_argument("--apply", action="store_true", help="Write files to disk (default: dry-run)")
    gen_p.set_defaults(func=cmd_generate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
