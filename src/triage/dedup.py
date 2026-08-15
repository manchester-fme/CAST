#!/usr/bin/env python3
"""Procedure Dedup:

Input: .tar.gz bug archives
Output: deduplicated triggers
    IN (solver, crash, crash_msg, DATATYPE_BITSTRING, size)
    OUT (solver, crash, crash_msg, DATATYPE_BITSTRING, size)

Solver invocation  and the crash signature list mirror
yinyang's src/core/Solver.py and config/Config.py:
https://github.com/testsmt/yinyang/blob/e5f1c13eb4df8f54f6556c9869d5e21299df0fc3/yinyang/src/core/Solver.py
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ERR_USAGE = 2

# full crash list from yinyang/config/Config.py
CRASH_SIGNATURES = [
    "Exception",
    "lang.AssertionError",
    "lang.Error",
    "runtime error",
    "LEAKED",
    "Leaked",
    "Segmentation fault",
    "segmentation fault",
    "segfault",
    "ASSERTION",
    "Assertion",
    "Fatal failure",
    "Internal error detected",
    "an invalid model was generated",
    "Failed to verify",
    "failed to verify",
    "ERROR: AddressSanitizer:",
    "invalid expression",
    "Aborted",
]


def solve(cil, file, timeout=5, debug=False):
    """Same as yinyang's Solver.solve (src/core/Solver.py)."""
    try:
        cmd = list(filter(None, cil.split(" "))) + [str(file)]
        if debug:
            print("cmd: " + " ".join(cmd), flush=True)
        output = subprocess.run(
            cmd,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )

    except subprocess.TimeoutExpired as te:
        if te.stdout and te.stderr:
            stdout = te.stdout.decode()
            stderr = te.stderr.decode()
        else:
            stdout = ""
            stderr = ""
        return stdout, stderr, 137

    except ValueError:
        stdout = ""
        stderr = ""
        return stdout, stderr, 0

    except FileNotFoundError:
        print('error: solver "' + cmd[0] + '" not found', flush=True)
        exit(2)

    stdout = output.stdout.decode()
    stderr = output.stderr.decode()
    returncode = output.returncode

    if debug:
        print("output: " + stdout + "\n" + stderr)

    return stdout, stderr, returncode


def run_solver(cil, smt2_file):
    """Wraps solve() with a verdict; verdict is 'sat', 'unsat', 'crash' or 'unknown'."""
    stdout, stderr, _ = solve(cil, smt2_file)
    output = stdout + stderr

    for sig in CRASH_SIGNATURES:
        if sig in output:
            return "crash", output
    if "unsat" in output:
        return "unsat", output
    if "sat" in output:
        return "sat", output
    return "unknown", output


def check_solver_installed(cil):
    """Smoke-test a solver on a trivially satisfiable query before the
    main dedup loop runs. A broken/invalid installation (e.g. missing
    shared libs) must fail loudly here -- if instead it's only caught
    per-file inside dedup(), its garbage output doesn't match any known
    crash signature, so it gets silently returned as an "unknown"
    verdict and misread downstream as real crash/unknown oracle
    evidence, producing false-positive soundness bugs."""
    with tempfile.TemporaryDirectory() as d:
        smoke_file = Path(d) / "smoke.smt2"
        smoke_file.write_text("(set-logic ALL)\n(assert true)\n(check-sat)\n")
        verdict, output = run_solver(cil, smoke_file)

    if verdict != "sat":
        print(
            'error: solver "' + cil.split(" ")[0] + '" failed a basic '
            "sanity check (expected sat on a trivial query, got '"
            + verdict + "') -- check the installation:\n" + output,
            flush=True,
        )
        exit(ERR_USAGE)


def crash_msg(output):
    for sig in CRASH_SIGNATURES:
        if sig in output:
            return sig
    return "unknown_crash"


def datatype_bitstring(smt2_text):
    """Stand-in for docs/architecture.txt's DATATYPE_BITSTRING: one bit per
    SMT-LIB sort mentioned in the file."""
    sorts = ["Bool", "Int", "Real", "BitVec", "Array", "String"]
    return "".join("1" if s in smt2_text else "0" for s in sorts)


_SYMBOL_RE = re.compile(r"\|[^|]*\||[^\s()]+")


def _read_symbol(s):
    """Read one SMT-LIB symbol (quoted |...| or plain token) from the start of s."""
    m = _SYMBOL_RE.match(s)
    if not m:
        return None, s
    tok = m.group(0)
    name = tok[1:-1] if tok.startswith("|") else tok
    return name, s[m.end():].lstrip()


def split_toplevel_forms(text):
    """Split SMT-LIB source into its top-level parenthesized forms, skipping
    line comments and treating quoted strings/symbols (";", '"..."', '|...|')
    as opaque so their parens don't affect nesting depth."""
    forms = []
    depth = 0
    start = None
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == ";":
            while i < n and text[i] != "\n":
                i += 1
        elif c == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 1
            i += 1
        elif c == "|":
            i += 1
            while i < n and text[i] != "|":
                i += 1
            i += 1
        elif c == "(":
            if depth == 0:
                start = i
            depth += 1
            i += 1
        elif c == ")":
            depth -= 1
            i += 1
            if depth == 0 and start is not None:
                forms.append(text[start:i])
                start = None
        else:
            i += 1
    return forms


def parse_decl_name(form):
    """If form is '(declare-const NAME TYPE)' or a nullary
    '(declare-fun NAME () TYPE)', return NAME, else None."""
    body = form.strip()
    if not (body.startswith("(") and body.endswith(")")):
        return None
    body = body[1:-1].strip()
    for kw in ("declare-const", "declare-fun"):
        if body.startswith(kw) and body[len(kw):len(kw) + 1] in (" ", "\t", "\n", ""):
            name, rest = _read_symbol(body[len(kw):].lstrip())
            if kw == "declare-fun" and not rest.startswith("()"):
                return None  # only nullary symbols can be grounded by substitution
            return name
    return None


def parse_define_name(form):
    """If form is a nullary '(define-fun NAME () TYPE VALUE)', return NAME,
    else None (non-nullary model entries, e.g. uninterpreted functions,
    can't be grounded by simple substitution)."""
    body = form.strip()
    if not (body.startswith("(") and body.endswith(")")):
        return None
    body = body[1:-1].strip()
    if not body.startswith("define-fun"):
        return None
    name, rest = _read_symbol(body[len("define-fun"):].lstrip())
    if not rest.startswith("()"):
        return None
    return name


def _collect_model_defs(forms, model_defs):
    for form in forms:
        name = parse_define_name(form)
        if name is not None:
            model_defs[name] = form
        else:
            inner = form.strip()
            if inner.startswith("(") and inner.endswith(")"):
                # unwrap solver-specific wrappers, e.g. z3's "(model ...)"
                # or cvc5's bare "( (define-fun ...) ... )"
                _collect_model_defs(split_toplevel_forms(inner[1:-1]), model_defs)


def ground_formula(orig_text, model_output):
    """Ground a formula by substituting each declared nullary symbol with its
    concrete value from a solver's (get-model) output, i.e. turn 'declare-const
    x Int' + model 'x = 3' into 'define-fun x () Int 3'. The result has no free
    variables left for the symbols the model covers, so re-solving it checks
    whether the model actually satisfies the original assertions."""
    model_defs = {}
    _collect_model_defs(split_toplevel_forms(model_output), model_defs)

    new_forms = []
    for form in split_toplevel_forms(orig_text):
        head = form.strip()[1:].lstrip()
        if head.startswith(("check-sat", "get-model", "get-value", "exit")):
            continue  # drop trailing commands, we append our own check-sat
        name = parse_decl_name(form)
        new_forms.append(model_defs[name] if name in model_defs else form)
    new_forms.append("(check-sat)")
    return "\n".join(new_forms) + "\n"


def get_model_output(cil, formula_text):
    """Re-run a solver with (get-model) appended and return its raw output."""
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "getmodel.smt2"
        f.write_text(formula_text + "\n(get-model)\n")
        stdout, stderr, _ = solve(cil, f)
    return stdout + stderr


def classify(path: Path):
    """Bug triggers are named 'incorrect-...smt2' (soundness) or
    'crash-...smt2' (crash)"""
    name = path.name
    if name.startswith("incorrect-"):
        return "soundness"
    if name.startswith("crash-"):
        return "crash"
    return None


def add_to_D(D, tup, path):
    solver, kind, msg, dtype, size = tup
    for i, (existing_tup, _) in enumerate(D):
        e_solver, e_kind, e_msg, e_dtype, e_size = existing_tup
        if (solver, kind, msg, dtype) == (e_solver, e_kind, e_msg, e_dtype):
            # 3.2.4.1: only keep the smaller reproducer for the same bug
            if size < e_size:
                D[i] = (tup, path)
            return
    # 3.2.4.2
    D.append((tup, path))


DEBUG = bool(os.environ.get("CAST_TRIAGE_DEBUG"))


def _dbg(path, msg):
    if DEBUG:
        print(f"[triage-debug] {path.name}: {msg}", file=sys.stderr, flush=True)


def confirm_crash(path, target_cmd):
    """Return the matched crash signature if target_cmd still crashes on
    path, else None. Shared with reduce.py's interestingness test so a
    reduction is judged by the exact same rule dedup() uses."""
    verdict, output = run_solver(target_cmd, path)
    if verdict != "crash":
        _dbg(path, f"crash not reconfirmed -- target verdict was '{verdict}', output: {output[:300]!r}")
        return None
    return crash_msg(output)


def confirm_soundness(path, text, target_cmd, oracle_cmd):
    """Return 'solution' or 'refutational' if target_cmd currently has a
    confirmed soundness bug on path, else None. Shared with reduce.py's
    interestingness test -- see the module docstring's 3.2 for the
    model-grounding cross-check this implements."""
    target_name = target_cmd.split(" ")[0]
    oracle_name = oracle_cmd.split(" ")[0]

    # 3.1: soundness bug must reproduce on S_target
    target_verdict, target_out = run_solver(target_cmd, path)
    oracle_verdict, oracle_out = run_solver(oracle_cmd, path)

    if target_verdict not in ("sat", "unsat"):
        _dbg(path, f"target gave no definitive verdict: '{target_verdict}', output: {target_out[:300]!r}")
        return None  # target itself gave no definitive verdict
    if oracle_verdict not in ("sat", "unsat") or oracle_verdict == target_verdict:
        _dbg(path, f"no disagreement -- target='{target_verdict}' oracle='{oracle_verdict}', oracle output: {oracle_out[:300]!r}")
        return None  # no definitive disagreement between target and oracle

    # 3.2: one solver said sat, the other unsat. Take the sat side's model,
    # ground it into the formula (substitute each declared symbol with its
    # concrete model value), and re-check the now fully-concrete formula
    # with both solvers:
    #  - both sat   -> the model genuinely satisfies the formula, so the
    #                  unsat-side verdict was wrong
    #  - both unsat -> the model does NOT satisfy the formula, so the
    #                  sat-side verdict (and its model) was wrong
    #  - otherwise  -> inconclusive
    if target_verdict == "sat":
        sat_cmd, sat_solver, unsat_solver = target_cmd, target_name, oracle_name
    else:
        sat_cmd, sat_solver, unsat_solver = oracle_cmd, oracle_name, target_name

    model_output = get_model_output(sat_cmd, text)
    validation_text = ground_formula(text, model_output)

    with tempfile.TemporaryDirectory() as d:
        vfile = Path(d) / "validate.smt2"
        vfile.write_text(validation_text)
        check_target, _ = run_solver(target_cmd, vfile)
        check_oracle, _ = run_solver(oracle_cmd, vfile)

    if check_target == "sat" and check_oracle == "sat":
        wrong_solver = unsat_solver  # S2 was wrong
    elif check_target == "unsat" and check_oracle == "unsat":
        wrong_solver = sat_solver  # S1 was wrong
    else:
        _dbg(path, f"grounded validation formula inconclusive -- target='{check_target}' oracle='{check_oracle}' (target_verdict was '{target_verdict}', oracle_verdict was '{oracle_verdict}')")
        return None  # validation formula itself inconclusive

    if wrong_solver != target_name:
        _dbg(path, f"model-grounding blames the oracle ({wrong_solver}), not the target -- target_verdict='{target_verdict}' oracle_verdict='{oracle_verdict}'")
        return None  # bug is in the oracle, not the target we're triaging

    # target's own verdict tells us which soundness property broke:
    # sat-with-invalid-model violates solution soundness, wrongly claiming
    # unsat (a satisfying model exists) violates refutation soundness.
    return "solution" if target_verdict == "sat" else "refutational"


def dedup(bug_files, target_cmd, oracle_cmd):
    check_solver_installed(target_cmd)
    check_solver_installed(oracle_cmd)

    target_name = target_cmd.split(" ")[0]

    D = []  # deduplicated triggers
    IN = []  # every tuple produced before dedup, i.e. dedup's input

    for path in bug_files:
        kind = classify(path)
        if kind is None:
            continue

        text = path.read_text(errors="ignore")
        size = path.stat().st_size

        if kind == "soundness":
            msg = confirm_soundness(path, text, target_cmd, oracle_cmd)
        else:  # crash
            msg = confirm_crash(path, target_cmd)

        if msg is None:
            continue  # trigger no longer reproduces / bug not in target
        tup = (target_name, kind, msg, datatype_bitstring(text), size)

        IN.append((tup, path))
        add_to_D(D, tup, path)

    return IN, D


def main(archive_path, target_cmd, oracle_cmd, out_dir):
    with tempfile.TemporaryDirectory() as extract_dir:
        try:
            shutil.unpack_archive(archive_path, extract_dir)
        except (FileNotFoundError, shutil.ReadError) as e:
            print(f'error: could not read archive "{archive_path}": {e}', flush=True)
            exit(ERR_USAGE)
        bug_files = sorted(Path(extract_dir).rglob("*.smt2"))
        IN, D = dedup(bug_files, target_cmd, oracle_cmd)
        print(f"Dedup identified {len(D)} unique bugs out of the {len(bug_files)} triggers")
        print("IN tuples:")
        for tup, path in IN:
            print(tup, path.name)
        print("OUT tuples:")
        for tup, path in D:
            print(tup, path.name)

        # dump the deduplicated triggers to disk -- bug_files only live
        # inside this TemporaryDirectory, so this has to happen before it's
        # cleaned up on exit. Each run gets its own folder (named after the
        # archive + target solver) so separate runs never mix their outputs.
        archive_stem = Path(archive_path).name
        for ext in (".tar.gz", ".tgz", ".zip"):
            if archive_stem.endswith(ext):
                archive_stem = archive_stem[: -len(ext)]
                break
        target_name = target_cmd.split(" ")[0]
        run_out_dir = Path(out_dir) / f"{archive_stem}__{target_name}"
        run_out_dir.mkdir(parents=True, exist_ok=True)
        for _, path in D:
            shutil.copy2(path, run_out_dir / path.name)
        print(f"Dumped {len(D)} deduplicated triggers to {run_out_dir}")

def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="dedup.py",
        description=(
            "Dedup bug triggers from a yinyang-style archive of "
            "incorrect-*.smt2 / crash-*.smt2 files."
        ),
    )
    parser.add_argument(
        "archive_path",
        help="path to an archive (.zip, .tar.gz, ...) containing the bug triggers",
    )
    parser.add_argument(
        "--target-cmd",
        required=True,
        help="target solver command line, e.g. 'z3 model_validate=true'",
    )
    parser.add_argument(
        "--oracle-cmd",
        required=True,
        help="oracle solver command line, e.g. 'cvc5 --check-models --check-proofs -q'",
    )
    parser.add_argument(
        "--out-dir",
        default="dedup_out",
        help="directory to dump the deduplicated (OUT) trigger files into (default: %(default)s)",
    )
    return parser.parse_args(argv)

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    main(args.archive_path, args.target_cmd, args.oracle_cmd, args.out_dir)
