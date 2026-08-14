"""Shared logic for the deterministic fake-solver scripts used by
test_dedup.py (fake_target_solver.py / fake_oracle_solver.py /
fake_broken_solver.py). A verdict is driven entirely by (set-info ...)
directives embedded in the .smt2 file, so behavior across dedup.py's three
solver calls per soundness trigger -- original query, (get-model) query,
grounded-validation query -- can be scripted deterministically without
needing real z3/cvc5 installed.

Directives are plain SMT-LIB set-info forms, so they pass through
dedup.ground_formula() untouched and survive from the original query into
the grounded validation query:

  (set-info :fake-<role>-verdict "sat"|"unsat"|"unknown"|"crash:<msg>")
      verdict for the original (ungrounded) query, keyed by role
  (set-info :fake-<role>-check "sat"|"unsat"|"unknown")
      verdict for the grounded validation query, keyed by role
  (set-info :fake-model "<smt-text-of-the-model>")
      raw text printed after "sat" when asked for a model

Which of these applies is inferred from the file content (with quoted
"..." string contents blanked out first, so a :fake-model value that
itself contains "(define-fun" can't be mistaken for the real thing):
"(get-model)" present -> a model request; "(define-fun" present (only
dedup.ground_formula() introduces this outside a quoted string) -> the
grounded validation query; otherwise -> the original query. A missing
verdict directive on the original query falls back to `default` (itself
"sat" by convention), so a directive-free smoke-test query (see
dedup.check_solver_installed) passes.

Each role gets its own launcher script (fake_target_solver.py /
fake_oracle_solver.py) rather than a shared "--role" flag so that
target_cmd.split(" ")[0] and oracle_cmd.split(" ")[0] -- how dedup.py
derives each tuple's solver name -- are genuinely distinct, the same way
"z3 ..." and "cvc5 ..." are.
"""
import re
import sys
from pathlib import Path

DIRECTIVE_RE = r'\(set-info\s+:{key}\s+"((?:[^"\\]|\\.)*)"\)'


def _directive(content, key):
    m = re.search(DIRECTIVE_RE.format(key=re.escape(key)), content)
    return m.group(1) if m else None


def _strip_quoted(content):
    return re.sub(r'"(?:[^"\\]|\\.)*"', '""', content)


def run(role, default="sat", argv=None):
    args = sys.argv[1:] if argv is None else argv
    content = Path(args[-1]).read_text()
    code = _strip_quoted(content)

    if "(get-model)" in code:
        print("sat")
        print(_directive(content, "fake-model") or "")
        return

    if "(define-fun" in code:
        verdict = _directive(content, f"fake-{role}-check") or "unknown"
    else:
        verdict = _directive(content, f"fake-{role}-verdict") or default

    if verdict.startswith("crash:"):
        print(verdict[len("crash:"):])
    else:
        print(verdict)
