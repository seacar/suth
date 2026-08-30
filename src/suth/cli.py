import argparse
import json
import sys

from suth.brain.interface import get_brain
from suth.compare import compare_runs
from suth.config import load_config
from suth.db import Memory, get_engine
from suth.objective import ObjectiveCheck
from suth.orchestrator import BudgetExceededError, ConcurrencyLimitError, Orchestrator
from suth.personas import load_persona, load_persona_from_db
from suth.session import SessionResult
from suth.watch import watch_and_rerun


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_test.py", description="Drive a real browser against a real objective."
    )
    parser.add_argument("--config", required=True, help="path to suth_config.json")
    parser.add_argument("--objective", required=True, help="free-text objective override")
    persona_group = parser.add_mutually_exclusive_group()
    persona_group.add_argument("--persona", help="single persona id")
    persona_group.add_argument(
        "--personas",
        help="comma-separated persona ids — runs them as one batch, in "
        "parallel (queued past the concurrency cap, not rejected), with a "
        "combined report. Falls back to ALL of suth_config.json's "
        "default_personas if neither --persona nor --personas is given.",
    )
    parser.add_argument("--environment", default="dev")
    parser.add_argument(
        "--caller",
        default="cli",
        help="caller id for budget/concurrency accounting (CI job, MCP client, ...)",
    )
    parser.add_argument("--headed", dest="headed", action="store_true", default=None)
    parser.add_argument("--headless", dest="headed", action="store_false")
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="skip Postgres logging and load the persona from the YAML library "
        "instead of Postgres (for quick local iteration without `specific dev`)",
    )
    check = parser.add_mutually_exclusive_group()
    check.add_argument(
        "--expect-url-pattern",
        help="Silent Failure detector: regex the final URL must match for the "
        "objective to count as met",
    )
    check.add_argument(
        "--expect-dom-text",
        help="Silent Failure detector: text that must be visible on the page "
        "for the objective to count as met",
    )
    parser.add_argument(
        "--step", action="store_true", help="pause for a keypress after every step (single-persona runs only)"
    )
    parser.add_argument(
        "--watch",
        metavar="PATH",
        help="re-run whenever PATH (file or directory) changes, e.g. the "
        "target project's build output",
    )
    parser.add_argument(
        "--export-transcript",
        metavar="PATH",
        help="write the full transcript (steps, failures, verdict) as JSON to "
        "PATH — for CI to upload as a build artifact (single-persona runs only)",
    )
    parser.add_argument(
        "--compare-baseline",
        metavar="SESSION_ID",
        help="CI gate: after running, compare this run's friction score "
        "against a baseline session and exit non-zero on regression "
        "(single-persona runs only)",
    )
    parser.add_argument(
        "--regression-threshold",
        type=float,
        default=0.0,
        help="friction-score increase over baseline allowed before --compare-baseline "
        "counts it as a regression (default: any increase)",
    )
    return parser


def _export_transcript(memory: Memory, session_id: str, path: str) -> None:
    session = memory.get_session(session_id)
    steps = memory.get_steps(session_id)
    failures = memory.get_failures(session_id)
    with open(path, "w") as f:
        json.dump({"session": session, "steps": steps, "failures": failures}, f, default=str, indent=2)
    print(f"transcript exported to {path}")


def _print_summary(result: SessionResult) -> None:
    print()
    print("=== SUTH run summary ===")
    print(f"session_id:        {result.session_id}")
    print(f"verdict:           {result.verdict}")
    print(f"steps taken:       {result.step_count}")
    print(f"final frustration: {result.final_frustration}")
    print(f"friction score:    {result.friction_score}")
    if result.failures:
        print(f"failure hits:      {len(result.failures)}")
        for hit in result.failures:
            print(f"  - step {hit.step_index}: {hit.taxonomy_label} — {hit.detail}")


def _print_batch_summary(batch_id: str, members: list) -> None:
    print()
    print(f"=== SUTH batch summary ({batch_id}) ===")
    print(f"{'persona':<32} {'verdict':<20} {'friction':>8}  session_id")
    for m in sorted(members, key=lambda m: m.persona_id):
        if m.result:
            print(f"{m.persona_id:<32} {m.result.verdict:<20} {m.result.friction_score:>8.1f}  {m.session_id}")
        else:
            print(f"{m.persona_id:<32} {'ERROR':<20} {'-':>8}  {m.session_id}  ({m.error})")

    scored = [m.result for m in members if m.result]
    failed = [m for m in members if not m.result]
    if scored:
        worst = max(scored, key=lambda r: r.friction_score)
        avg = sum(r.friction_score for r in scored) / len(scored)
        print(f"\naverage friction: {avg:.1f}   worst: {worst.persona_id} ({worst.verdict}, {worst.friction_score:.1f})")
    if failed:
        print(f"{len(failed)} of {len(members)} persona(s) errored — see above")


def _resolve_persona_ids(args, config) -> list[str]:
    if args.personas:
        return [p.strip() for p in args.personas.split(",") if p.strip()]
    if args.persona:
        return [args.persona]
    return list(config.default_personas)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    config = load_config(args.config)
    resolved = config.resolve(args.environment)
    if args.headed is not None:
        resolved.headed = args.headed

    persona_ids = _resolve_persona_ids(args, config)
    if not persona_ids:
        print("no --persona/--personas given and config has no default_personas", file=sys.stderr)
        return 1

    memory = None if args.no_db else Memory(get_engine())
    load_one = (lambda pid: load_persona(pid)) if args.no_db else (lambda pid: load_persona_from_db(memory.engine, pid))

    objective_check = None
    if args.expect_url_pattern:
        objective_check = ObjectiveCheck(type="url_pattern", value=args.expect_url_pattern)
    elif args.expect_dom_text:
        objective_check = ObjectiveCheck(type="dom_text", value=args.expect_dom_text)

    orchestrator = Orchestrator(memory=memory)
    exit_code = 0

    def on_step(step_index, record):
        input(f"[step {step_index}] {record.action_type} on {record.target} -> Enter to continue...")

    def run_single(persona_id: str) -> int:
        nonlocal exit_code
        persona = load_one(persona_id)
        brain = get_brain(resolved.provider_profile)
        print(f"Running '{persona_id}' (v{persona.version}) against {resolved.base_url}")
        print(f"Objective: {args.objective}")
        try:
            session_id = orchestrator.start_session(
                config=resolved, persona=persona, objective=args.objective, brain=brain,
                environment=args.environment, caller=args.caller, objective_check=objective_check,
                on_step=on_step if args.step else None,
            )
        except (ConcurrencyLimitError, BudgetExceededError) as e:
            print(f"run rejected: {e}", file=sys.stderr)
            return 1

        result = orchestrator.get_report(session_id)
        _print_summary(result)

        if args.export_transcript:
            if memory is None:
                print("--export-transcript needs Postgres logging (drop --no-db)", file=sys.stderr)
            else:
                _export_transcript(memory, result.session_id, args.export_transcript)

        exit_code = 0
        if args.compare_baseline:
            if memory is None:
                print("--compare-baseline needs Postgres logging (drop --no-db)", file=sys.stderr)
                exit_code = 1
            else:
                comparison = compare_runs(memory, args.compare_baseline, result.session_id, args.regression_threshold)
                print()
                print("=== compare_runs ===")
                print(f"baseline:  {comparison.baseline_session_id} score={comparison.baseline_friction_score}")
                print(f"candidate: {comparison.candidate_session_id} score={comparison.candidate_friction_score}")
                print(f"delta:     {comparison.friction_delta:+.1f}")
                if comparison.regressed:
                    print("REGRESSION: candidate friction score exceeds baseline past threshold")
                    exit_code = 1
        return exit_code

    def run_batch(ids: list[str]) -> int:
        if args.step:
            print("note: --step is ignored for multi-persona runs", file=sys.stderr)
        if args.export_transcript or args.compare_baseline:
            print("note: --export-transcript/--compare-baseline are ignored for multi-persona runs", file=sys.stderr)

        personas = [load_one(pid) for pid in ids]
        print(f"Running {len(ids)} personas in parallel against {resolved.base_url}: {', '.join(ids)}")
        print(f"Objective: {args.objective}")
        try:
            batch_id = orchestrator.start_batch(
                config=resolved, personas=personas, objective=args.objective,
                brain_factory=lambda: get_brain(resolved.provider_profile),
                environment=args.environment, caller=args.caller, objective_check=objective_check,
            )
        except BudgetExceededError as e:
            print(f"batch rejected: {e}", file=sys.stderr)
            return 1

        members = orchestrator.get_batch_report(batch_id)
        _print_batch_summary(batch_id, members)
        return 1 if any(m.error for m in members) else 0

    def run_once() -> int:
        nonlocal exit_code
        exit_code = run_batch(persona_ids) if len(persona_ids) > 1 else run_single(persona_ids[0])
        return exit_code

    if args.watch:
        watch_and_rerun(args.watch, lambda: run_once())
        return 0
    return run_once()


if __name__ == "__main__":
    raise SystemExit(main())
