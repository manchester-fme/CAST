#!/usr/bin/env python3
"""Procedure Main (see docs/architecture.txt / docs/triage.txt):

Dedup -> Reduce -> Dedup -> Report

Runs the full triage pipeline against a bug archive by calling the other
three scripts as library functions (dedup.dedup(), reduce.reduce(),
report.report()) rather than shelling out to them:

  1. dedup    confirm + deduplicate triggers straight from the archive
  2. reduce   minimize each deduplicated trigger with creduce
  3. dedup    re-confirm + re-dedup the *minimized* triggers -- reduction
              happens per-trigger in isolation, so it can (rarely) change
              which crash signature a trigger matches, or collapse two
              previously-distinct triggers onto the same signature once
              both are minimal
  4. report   draft (or, with --post, file) a GitHub issue per trigger
              that survives step 3

A failure isolated to one trigger (reduce.py or report.py exiting instead
of completing) is logged and skipped rather than aborting the whole run.
"""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import dedup
import reduce
import report

ERR_USAGE = 2


def stage1_dedup(archive_path, target_cmd, oracle_cmd, dedup_out):
    with tempfile.TemporaryDirectory() as extract_dir:
        try:
            shutil.unpack_archive(archive_path, extract_dir)
        except (FileNotFoundError, shutil.ReadError) as e:
            print(f'error: could not read archive "{archive_path}": {e}', flush=True)
            exit(ERR_USAGE)
        bug_files = sorted(Path(extract_dir).rglob("*.smt2"))
        _, D = dedup.dedup(bug_files, target_cmd, oracle_cmd)
        print(f"[1/4] dedup: {len(D)} unique bugs out of {len(bug_files)} triggers", flush=True)

        # bug_files only live inside this TemporaryDirectory, so copy the
        # survivors out before it's cleaned up on exit.
        dedup_out.mkdir(parents=True, exist_ok=True)
        confirmed = []
        for _, path in D:
            dest = dedup_out / path.name
            shutil.copy2(path, dest)
            confirmed.append(dest)
        return confirmed


def stage2_reduce(confirmed, target_cmd, oracle_cmd, reduced_out, creduce_bin, jobs):
    reduced = []
    for path in confirmed:
        print(f"[2/4] reduce: {path.name}", flush=True)
        oracle_for_kind = oracle_cmd if dedup.classify(path) == "soundness" else None
        try:
            work_file = reduce.reduce(path, target_cmd, oracle_for_kind, reduced_out, creduce_bin, jobs)
        except SystemExit as e:
            print(f"  skipped {path.name}: reduce.py exited with code {e.code}", flush=True)
            continue
        reduced.append(work_file)
    return reduced


def stage3_redup(reduced, target_cmd, oracle_cmd):
    _, D = dedup.dedup(reduced, target_cmd, oracle_cmd)
    print(
        f"[3/4] re-dedup after reduction: {len(D)} unique bugs out of {len(reduced)} minimized triggers",
        flush=True,
    )
    if len(D) < len(reduced):
        print("  note: reduction merged some previously-distinct triggers onto the same bug signature", flush=True)
    return [path for _, path in D]


def stage4_report(final_triggers, target_cmd, oracle_cmd, post, repo):
    for path in final_triggers:
        print(f"[4/4] report: {path.name}", flush=True)
        oracle_for_kind = oracle_cmd if dedup.classify(path) == "soundness" else None
        try:
            report.report(path, target_cmd, oracle_for_kind, post, out=None, repo=repo)
        except SystemExit as e:
            print(f"  skipped {path.name}: report.py exited with code {e.code}", flush=True)


def triage(archive_path, target_cmd, oracle_cmd, out_dir, post, creduce_bin, jobs, repo=None):
    dedup.check_solver_installed(target_cmd)
    dedup.check_solver_installed(oracle_cmd)

    out_dir = Path(out_dir)
    dedup_out = out_dir / "dedup_out"
    reduced_out = out_dir / "reduced_out"

    confirmed = stage1_dedup(archive_path, target_cmd, oracle_cmd, dedup_out)
    if not confirmed:
        print("no confirmed bugs -- nothing to reduce or report", flush=True)
        return

    reduced = stage2_reduce(confirmed, target_cmd, oracle_cmd, reduced_out, creduce_bin, jobs)
    if not reduced:
        print("no triggers survived reduction -- nothing to report", flush=True)
        return

    final_triggers = stage3_redup(reduced, target_cmd, oracle_cmd)
    if not final_triggers:
        print("no triggers survived the post-reduction re-check -- nothing to report", flush=True)
        return

    stage4_report(final_triggers, target_cmd, oracle_cmd, post, repo)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="triage.py",
        description="Run the full Dedup -> Reduce -> Dedup -> Report pipeline against a bug archive.",
    )
    parser.add_argument("archive_path", help="path to an archive (.zip, .tar.gz, ...) containing bug triggers")
    parser.add_argument(
        "--target-cmd",
        required=True,
        help="target solver command line, e.g. 'z3 model_validate=true'",
    )
    parser.add_argument(
        "--oracle-cmd",
        required=True,
        help="oracle solver command line, e.g. 'cvc5 --check-models --check-proofs'",
    )
    parser.add_argument(
        "--out-dir",
        default="triage_out",
        help="directory for this run's dedup_out/ and reduced_out/ (default: %(default)s)",
    )
    parser.add_argument(
        "--post",
        action="store_true",
        help="actually file issues with `gh issue create` (default: dry run, print only)",
    )
    parser.add_argument("--creduce-bin", default="creduce", help="creduce executable (default: %(default)s)")
    parser.add_argument("--jobs", "-j", type=int, default=None, help="parallel creduce jobs (creduce --n)")
    parser.add_argument(
        "--repo",
        help="file issues on this repo (owner/name) instead of the current directory's git remote",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    triage(
        args.archive_path, args.target_cmd, args.oracle_cmd, args.out_dir, args.post,
        args.creduce_bin, args.jobs, args.repo,
    )
