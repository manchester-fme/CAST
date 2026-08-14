# Real archive fixtures

Two of the repo's real bug-fuzzing archives, committed here (excepted from
the top-level `.gitignore`'s blanket `*.tar.gz` rule) so
`RealSolverRegressionTest` in `tests/test_dedup.py` always has something to
run against real z3/cvc5, not only when a `.tar.gz` happens to be sitting
in the repo root.

- `manchester-fme_cvc5_solvers_cvc5_bugs_bugs-be30d27-1786498865.tar.gz` --
  cvc5-origin fuzzing run; with z3 as target this confirms a real
  refutation-soundness bug.
- `manchester-fme_z3_solvers_z3_bugs_bugs-9167020-1786525852.tar.gz` --
  z3-origin fuzzing run; with z3 as target this confirms a real crash
  (`an invalid model was generated`).

Both are tiny (under 2 KB) and were picked to exercise a soundness trigger
and a crash trigger respectively. If one ever stops confirming after a
solver upgrade, swap in a fresh small archive from a real run.
