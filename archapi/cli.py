from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Optional

from archapi.config import ArchAPIConfig, ArchAPIConfigError, load_config
from archapi.core import ArchAPI
from archapi.llm.errors import LLMProviderError

# Exit codes (documented, not just implicit):
#   0  success
#   1  generation/validation rejected (PolicyGate, framework validation, or
#      a parse failure on the LLM's response)
#   2  invalid CLI usage or invalid/unsafe configuration
#   3  LLM provider failure (missing/invalid credentials, network/API error)
EXIT_OK = 0
EXIT_REJECTED = 1
EXIT_INVALID_USAGE = 2
EXIT_PROVIDER_FAILURE = 3


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, default=str))


def _print_error(message: str, debug: bool) -> None:
    print(f"error: {message}", file=sys.stderr)
    if debug:
        import traceback
        traceback.print_exc()


def _load_settings(path: str, overrides: Optional[Dict[str, Any]] = None) -> ArchAPIConfig:
    return load_config(path, overrides=overrides)


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------

def cmd_detect(args: argparse.Namespace) -> int:
    _load_settings(args.path)  # validated even though detect doesn't use LLM/retrieval settings
    api = ArchAPI(args.path)
    result = api.detect_framework()

    if args.json:
        _print_json({
            "framework": result.framework,
            "confidence": result.confidence,
            "reasons": result.reasons,
        })
    else:
        print(f"Framework: {result.framework}")
        print(f"Confidence: {result.confidence}")
        if result.reasons:
            print(f"Reasons: {', '.join(result.reasons)}")

    return EXIT_OK


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

def cmd_scan(args: argparse.Namespace) -> int:
    _load_settings(args.path)
    api = ArchAPI(args.path)
    api.detect_framework()
    scan = api.scan()

    counts = {
        "routes": len(scan.routes),
        "controllers": len(scan.controllers),
        "services": len(scan.services),
        "models": len(scan.models),
        "schemas": len(scan.schemas),
        "middleware": len(scan.middleware),
        "tests": len(scan.tests),
        "config_files": len(scan.config_files),
    }

    if args.json:
        _print_json({"framework": scan.framework, **counts})
    else:
        print(f"Framework: {scan.framework}")
        print()
        for label, count in counts.items():
            print(f"  {label.replace('_', ' ').capitalize()}: {count}")

    return EXIT_OK


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------

def cmd_plan(args: argparse.Namespace) -> int:
    _load_settings(args.path)
    api = ArchAPI(args.path)
    plan = api.plan_api(args.request)

    if args.json:
        _print_json({
            "method": plan.method,
            "path": plan.path,
            "entities": plan.entities,
            "layers": plan.layers,
            "generation_allowed": plan.generation_allowed,
            "reason": plan.reason,
        })
    else:
        print(f"Method: {plan.method}")
        print(f"Path: {plan.path}")
        print(f"Entities: {', '.join(plan.entities) if plan.entities else '(none)'}")
        print(f"Layers: {', '.join(plan.layers) if plan.layers else '(none)'}")
        print(f"Generation allowed: {'yes' if plan.generation_allowed else 'no'}")
        if plan.reason:
            print(f"Reason: {plan.reason}")

    return EXIT_OK


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------

def _generate_summary_dict(api: ArchAPI, result, use_llm: bool, dry_run: bool) -> Dict[str, Any]:
    """
    Structured, JSON-safe summary. Deliberately excludes anything the
    safety review flagged as off-limits for machine output: no raw prompt
    text, no generated file *content* (paths only), no credentials.
    """
    detection = api._detection
    retrieved_paths = []
    if use_llm and api._last_retrieved_context is not None:
        retrieved_paths = [item.path for item in api._last_retrieved_context.all_items()]

    architecture_score = None
    if result.files:
        try:
            architecture_score = api.score_architecture(result).percentage
        except Exception:
            architecture_score = None

    return {
        "framework": detection.framework if detection else None,
        "mode": "llm" if use_llm else "deterministic",
        "resource": result.plan.entities[-1] if result.plan.entities else None,
        "generation_allowed": result.validation_report.success,
        "dry_run": dry_run,
        "retrieved_paths": retrieved_paths,
        "generated_paths": [str(f.path) for f in result.files],
        "policy_gate_pass": result.policy_gate_pass,
        "framework_validation_pass": result.framework_validation_pass,
        "architecture_score": architecture_score,
        "errors": result.validation_report.errors,
        "warnings": result.warnings,
    }


def _render_generate_human(api: ArchAPI, result, use_llm: bool, dry_run: bool) -> str:
    detection = api._detection
    lines = [
        f"Framework: {detection.framework if detection else 'unknown'}",
        f"Mode: {'LLM' if use_llm else 'Deterministic'}",
        f"Resource: {result.plan.entities[-1] if result.plan.entities else 'unknown'}",
        f"Generation allowed: {'yes' if result.validation_report.success else 'no'}",
    ]

    if use_llm and api._last_retrieved_context is not None:
        retrieved = api._last_retrieved_context.all_items()
        if retrieved:
            lines.append("")
            lines.append("Retrieved context:")
            lines.extend(f"  {item.path}" for item in retrieved)

    lines.append("")
    if result.files:
        lines.append("Generated:")
        lines.extend(f"  {f.path}" for f in result.files)
    else:
        lines.append("Generated: (no files)")

    lines.append("")
    lines.append("Validation:")
    lines.append(f"  Policy gate: {'PASS' if result.policy_gate_pass else 'FAIL'}")
    lines.append(f"  Framework validation: {'PASS' if result.framework_validation_pass else 'FAIL'}")
    if result.files:
        try:
            score = api.score_architecture(result)
            lines.append(f"  Architecture score: {score.percentage:.0f}%")
        except Exception:
            pass

    if result.validation_report.errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"  {err}" for err in result.validation_report.errors)

    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"  {w}" for w in result.warnings)

    lines.append("")
    if not result.files:
        lines.append("No files generated.")
    elif not result.validation_report.success:
        lines.append("Blocked — no files written.")
    elif dry_run:
        lines.append("Dry run — no files written. Re-run with --apply to write files.")
    else:
        lines.append("Files written.")

    return "\n".join(lines)


def cmd_generate(args: argparse.Namespace) -> int:
    overrides: Dict[str, Any] = {}
    if args.llm:
        overrides["use_llm"] = True
    if args.model:
        overrides["llm_model"] = args.model

    settings = _load_settings(args.path, overrides=overrides)
    use_llm = settings.use_llm
    dry_run = not args.apply

    api = ArchAPI(args.path, settings=settings)
    api.detect_framework()

    result = api.generate_api(args.request, dry_run=dry_run)

    exit_code = EXIT_OK
    if not result.validation_report.success:
        exit_code = EXIT_REJECTED
        # core.py stamps this exact reason prefix for both LLM-provider
        # failure modes it catches internally (auth/network) rather than
        # raising -- used here only to pick the more specific exit code,
        # never to change whether generation is blocked.
        if result.plan.reason and result.plan.reason.startswith("LLM provider error"):
            exit_code = EXIT_PROVIDER_FAILURE

    if args.json:
        _print_json(_generate_summary_dict(api, result, use_llm, dry_run))
    else:
        print(_render_generate_human(api, result, use_llm, dry_run))

    return exit_code


# ---------------------------------------------------------------------------
# Parser / entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="archapi",
        description="Architecture-preserving REST API synthesis",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Show full tracebacks on unexpected errors (default: concise error messages)",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    detect_p = sub.add_parser("detect", help="Detect the framework of a project")
    detect_p.add_argument("path", nargs="?", default=".", help="Project path (default: .)")
    detect_p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    detect_p.set_defaults(func=cmd_detect)

    scan_p = sub.add_parser("scan", help="Scan project structure")
    scan_p.add_argument("path", nargs="?", default=".", help="Project path (default: .)")
    scan_p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    scan_p.set_defaults(func=cmd_scan)

    plan_p = sub.add_parser("plan", help="Plan an API without generating code (read-only)")
    plan_p.add_argument("path", nargs="?", default=".", help="Project path (default: .)")
    plan_p.add_argument("request", help="Natural-language API request, e.g. 'Create GET API for invoice'")
    plan_p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    plan_p.set_defaults(func=cmd_plan)

    gen_p = sub.add_parser("generate", help="Generate API code (dry-run by default)")
    gen_p.add_argument("path", nargs="?", default=".", help="Project path (default: .)")
    gen_p.add_argument("request", help="Natural-language API request")
    gen_p.add_argument("--llm", action="store_true", help="Use architecture-aware LLM generation (default: deterministic)")
    gen_p.add_argument("--model", default=None, help="Override the LLM model (implies nothing about --llm)")
    gen_p.add_argument("--apply", action="store_true", help="Write files to disk (default: dry-run preview)")
    gen_p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    gen_p.set_defaults(func=cmd_generate)

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    debug = getattr(args, "debug", False)

    try:
        return args.func(args)
    except ArchAPIConfigError as exc:
        _print_error(f"configuration error: {exc}", debug)
        return EXIT_INVALID_USAGE
    except FileNotFoundError as exc:
        _print_error(str(exc), debug)
        return EXIT_INVALID_USAGE
    except LLMProviderError as exc:
        # Raised directly (not returned in a result) when the provider
        # can't even be constructed -- e.g. no OPENAI_API_KEY set.
        _print_error(f"provider error: {exc}", debug)
        return EXIT_PROVIDER_FAILURE
    except Exception as exc:
        _print_error(str(exc), debug)
        return EXIT_INVALID_USAGE


if __name__ == "__main__":
    sys.exit(main())
