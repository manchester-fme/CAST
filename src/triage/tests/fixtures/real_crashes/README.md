# Real crash fixtures

Committed crash triggers pulled from actual z3/cvc5 fuzzing runs (originally
under `dedup_out/`), each minimized with `reduce.py` down to the smallest
input that still reproduces the same crash. Used by
`tests/test_dedup.py::RealCrashFixtureTests` to exercise
`dedup.confirm_crash()` against the real solvers deterministically, without
depending on a `.tar.gz` archive being present (those are gitignored).

| file                  | target solver             | expected crash_msg                |
|------------------------|----------------------------|------------------------------------|
| `z3-invalid-model.smt2` | `z3 model_validate=true`   | `an invalid model was generated`  |
| `cvc5-assertion.smt2`   | `cvc5 --check-models --check-proofs` | `ASSERTION`              |

`z3-invalid-model.smt2` reduces to a trivial division-by-zero query that
trips z3's own model validation. `cvc5-assertion.smt2` stays a few KB
because the crash is a regex-engine stack overflow -- it genuinely needs
deep `re.union`/`re.+`/`re.*` nesting to reproduce, so creduce can't shrink
it much further without losing the bug.

If either fixture stops reproducing after a solver upgrade (verdict or
crash message changes), regenerate it: find (or re-derive) a trigger from a
`dedup_out` run, then `python3 reduce.py <file> --target-cmd '...'` and
copy the result here.
