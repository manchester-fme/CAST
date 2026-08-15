### Triage

Takes the bug archives `fuzz` produces (`incorrect-*.smt2` soundness
triggers / `crash-*.smt2` crash triggers) and turns them into filed,
minimized, deduplicated GitHub issues. Lives in `src/triage/`.

### Components
- `dedup.py` -- confirms each trigger still reproduces and deduplicates.
- `reduce.py` -- minimizes a confirmed trigger with `creduce`.
- `report.py` -- drafts (or files) a GitHub issue for a confirmed trigger.
- `triage.py` -- runs all four pipeline stages against an archive in one go.

### Inputs
- A `.tar.gz`/`.zip` archive of `incorrect-*.smt2` / `crash-*.smt2` triggers
- Target solver command line (e.g. `z3 model_validate=true`)
- Oracle solver command line (e.g. `cvc5 --check-models --check-proofs -q`)

### Outputs
- Deduplicated, confirmed trigger files (`dedup_out/`)
- Minimized versions of those (`reduced_out/`)
- A `[CAST] ...` GitHub issue per surviving bug, or (dry run, the default)
  its drafted title/body printed to stdout

### Algorithm
1) Dedup (`dedup.dedup()`)
   - Classify each file by its `incorrect-`/`crash-` filename prefix.
   - Crash triggers: confirmed by matching a known crash signature
     (`dedup.CRASH_SIGNATURES`, mirroring yinyang's crash list) in the
     target solver's output.
   - Soundness triggers: target and oracle must give opposite definitive
     verdicts (one `sat`, one `unsat`). Take the `sat` side's model, ground
     it into the formula (substitute each declared symbol with its
     concrete value via `dedup.ground_formula()`), and re-check the now
     fully-concrete formula with both solvers:
     - both `sat` -> the model is genuine, so the `unsat` side was wrong
     - both `unsat` -> the model doesn't actually satisfy the formula, so
       the `sat` side (and its model) was wrong
     - otherwise -> inconclusive, drop the trigger
     Only kept if the *target* (not the oracle) turns out to be wrong.
     `target_verdict == sat` means a **solution**-soundness bug (invalid
     model); `target_verdict == unsat` means a **refutation**-soundness
     bug (wrongly claimed unsat).
   - Dedup key: `(solver, kind, msg, DATATYPE_BITSTRING)` -- `msg` is the
     matched crash signature, or `solution`/`refutational` for soundness.
     Keeps the smallest reproducer per key.

2) Reduce (`reduce.reduce()`)
   - Runs `creduce` against an interestingness test built from
     `dedup.confirm_crash()`/`dedup.confirm_soundness()` -- the exact same
     functions step 1 uses -- so a reduction can't wander into some other,
     unrelated bug, and a soundness reduction can't flip which soundness
     property broke partway through.

3) Dedup again (`triage.py` only)
   - Re-runs step 1 on the *minimized* triggers. Reduction happens
     per-trigger in isolation, so it can (rarely) change which signature a
     trigger matches, or collapse two previously-distinct triggers onto
     the same signature once both are minimal.

4) Report (`report.py`)
   - Title: `[CAST] {Solution|Refutational} Soundness bug related to
     <sorts>` or `[CAST] Crash: <msg> related to <sorts>` (sorts
     reverse-mapped from `DATATYPE_BITSTRING`).
   - Body: solver version, the exact commands run and their real output,
     then the (pretty-printed) formula, under a generic `bug.smt2` name
     since the real filename is an internal creduce-mangled one.
   - Dry run by default; `--post` files it with `gh issue create`, after
     checking for an existing issue with the same title to avoid
     duplicates.

### Running it
```
python3 src/triage/triage.py bugs.tar.gz \
  --target-cmd "z3 model_validate=true" \
  --oracle-cmd "cvc5 --check-models --check-proofs -q"
# add --post to actually file issues instead of a dry run
```
Or `.github/workflows/triage.yml`, both `workflow_dispatch` (manual) and
`workflow_call` (from a solver's `cast.yml` cycle -- see
`example/.github/workflows/cast.yml`). `--post` files real issues, so
`workflow_dispatch` defaults to a dry run.

`solver`/`repo_url`/`target_cmd`/`oracle_cmd` are always required;
`solver_dir`, `archive`, and `commit_hash` are optional. `solver_dir`
defaults to `src/solvers/<solver>`; set it the same way you would for
`build.yml`/`commit-fuzzer.yml` (e.g. `<solver>/.cast`) -- it's where
`manifest.json` is read from. `archive`/`commit_hash` left empty
auto-discover the most recently uploaded bug archive and production build
for `solver` from S3/R2 (the same state `build.yml`/`commit-fuzzer.yml`
write to, via `get_state_manager()`), or supply them explicitly to triage
one specific archive/commit (e.g. the two fixture archives in
`src/triage/tests/fixtures/archives/`).

Both solvers involved are always the exact ones fuzzing used, never an
installed-fresh substitute:
- Target: fetched as the exact binary `build.yml` built for the resolved
  commit (same S3/R2 key).
- Oracle: `repo_url` is shallow-cloned to read the target's
  `manifest.json` (`fuzzer.oracle_solver` / `oracle_fetch_fallback`), then
  installed via the exact same pip/script/github_release fallback
  `commit-fuzzer.yml`'s "Install oracle fallback" step uses -- the same
  install path real fuzzing runs take, since `oracle_solver_dir` is never
  set in `example/.github/workflows/cast.yml`.

Issues are filed on `repo` (default: the calling repo, e.g.
`manchester-fme/z3` when this workflow is called via `workflow_call` from
z3's own `cast.yml` -- not `manchester-fme/CAST`, even though the job
checks that out to get `src/triage/`). `report.py`/`triage.py`'s
`--repo` flag is what makes this possible: without it, `gh issue
create`/`gh issue list` infer the target from the current directory's
git remote, which after that checkout would always be CAST itself.

**Untested end-to-end as of writing** -- no local access to the org's
R2/AWS credentials to verify the broker namespace/key (or the
auto-discovery listing) against the real backend. Verify on a real run.

### Tests
`src/triage/tests/` is a hermetic suite of fake-solver-driven unit tests
covering every branch of `dedup.py`'s confirmation logic, plus real-solver
checks against committed fixtures (`src/triage/tests/fixtures/`). Run with
`python3 -m unittest discover -s src/triage/tests -v`.

### Not yet wired up
- No automatic short-hash -> full-hash resolution: `commit_hash` (when
  supplied explicitly rather than auto-discovered) must be the full hash.
