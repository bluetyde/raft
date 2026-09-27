"""Run every pre-merge check of this repo.

Usage:
    python scripts/premerge.py [--skip-python] [--skip-web] [--only NAME ...]
    python -m scripts.premerge [--skip-python] [--skip-web] [--only NAME ...]
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import inspect
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Stage:
    name: str
    cmd: list[str]
    cwd: str


@dataclass
class Result:
    name: str
    returncode: int
    seconds: float
    reason: str | None = None


def default_stages(repo_root: Path | str | None = None) -> list[Stage]:
    npm = shutil.which("npm")
    return [
        Stage("python", [sys.executable, "-B", "-m", "unittest"], "."),
        Stage("web-test", [npm, "test"], "web"),
        Stage("web-typecheck", [npm, "run", "typecheck"], "web"),
        Stage("web-build", [npm, "run", "build"], "web"),
    ]


def run_stages(stages: list[Stage], repo_root: Path | str | None = None) -> list[Result]:
    results: list[Result] = []
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    for stage in stages:
        cwd = Path(stage.cwd)
        if not cwd.is_absolute():
            cwd = root / cwd

        if not stage.cmd or stage.cmd[0] is None:
            results.append(Result(
                name=stage.name,
                returncode=127,
                seconds=0.0,
                reason="npm not found" if "web" in stage.name or "npm" in stage.name else "command not found",
            ))
            continue

        t0 = time.monotonic()
        try:
            proc = subprocess.run(stage.cmd, cwd=cwd)
            elapsed = time.monotonic() - t0
            results.append(Result(
                name=stage.name,
                returncode=proc.returncode,
                seconds=elapsed,
                reason=None,
            ))
        except FileNotFoundError:
            elapsed = time.monotonic() - t0
            reason = "npm not found" if stage.cmd and stage.cmd[0] in ("npm", "npm.cmd") else "command not found"
            results.append(Result(
                name=stage.name,
                returncode=127,
                seconds=elapsed,
                reason=reason,
            ))
    return results


def format_summary(results: list[Result]) -> str:
    headers = ("Stage", "Status", "Exit Code", "Seconds", "Reason")
    rows: list[tuple[str, str, str, str, str]] = []
    for r in results:
        status = "PASS" if r.returncode == 0 else "FAIL"
        sec_str = f"{r.seconds:.2f}s"
        reason_str = r.reason or ""
        rows.append((r.name, status, str(r.returncode), sec_str, reason_str))

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(val))

    lines = []
    lines.append("  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)).rstrip())
    lines.append("  ".join("-" * col_widths[i] for i in range(len(headers))))
    for row in rows:
        lines.append("  ".join(val.ljust(col_widths[i]) for i, val in enumerate(row)).rstrip())
    return "\n".join(lines)


def main(
    argv: list[str] | None = None,
    *,
    stages_factory: Callable[..., list[Stage]] = default_stages,
) -> int:
    parser = argparse.ArgumentParser(description="Run pre-merge checks.")
    parser.add_argument("--skip-python", action="store_true", help="skip python stage")
    parser.add_argument("--skip-web", action="store_true", help="skip web stages")
    parser.add_argument(
        "--only",
        action="append",
        metavar="NAME",
        dest="only",
        help="run only stage NAME (repeatable)",
    )
    args = parser.parse_args(argv)

    sig = inspect.signature(stages_factory)
    has_params = any(
        p.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        )
        for p in sig.parameters.values()
    )
    stages = stages_factory(REPO_ROOT) if has_params else stages_factory()

    selected = list(stages)
    if args.only:
        only_set = set(args.only)
        known_names = {s.name for s in stages}
        unknown = only_set - known_names
        if unknown:
            parser.error(f"unknown stage(s): {', '.join(sorted(unknown))}")
        selected = [s for s in selected if s.name in only_set]
    if args.skip_python:
        selected = [s for s in selected if s.name != "python"]
    if args.skip_web:
        selected = [s for s in selected if not s.name.startswith("web")]

    if not selected:
        parser.error("no stages selected")

    results = run_stages(selected, REPO_ROOT)
    print("\n" + format_summary(results))
    return 0 if all(r.returncode == 0 for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
