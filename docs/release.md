# Cutting a CAST Release

Three gates, then filing the release. Don't skip ahead - each gate is cheap
insurance against a different failure mode, and none of them subsume each
other (see "What each gate does *not* catch" below).

## 1. `pre-release.yml` passes for both z3 and cvc5

Dispatch `pre-release.yml` from each fork's own caller workflow (hardcoded to
that fork's pinned known-good commit + bug archive - see the file's header
in `manchester-fme/CAST` for how callers are wired). Both must pass:

- z3: commit `0bd679a`, expects a confirmed crash ("an invalid model was
  generated")
- cvc5: commit `be30d27`, expects a confirmed crash ("ASSERTION")

This proves triage's detection logic (build fetch, oracle install,
`dedup.dedup()`) still reconfirms known real bugs. It does not touch
build/fuzz, and does not exercise any cross-repo reusable-workflow chain.

## 2. Tag the release candidate commit

Lightweight tag only - **not** `git tag -a`/`-m`:

```
git tag vX.Y.Z <sha>
git push origin vX.Y.Z
```

Put the release description in a GitHub Release (`gh release create vX.Y.Z
--notes "..."`), not in the tag message. An annotated tag breaks nested
reusable-workflow calls that resolve relative to it (e.g.
`coverage-daily-check.yml`'s call to `./coverage-mapper.yml`) - see
https://github.com/orgs/community/discussions/55649. This is also documented
next to the `cast.yml` tag-pinning advice in the main README.

## 3. One full CAST cycle on z3 and cvc5, pinned to the new tag

Dispatch `cast.yml`'s `action: cycle` (or the underlying
`manager.yml`/`build.yml`/`commit-fuzzer.yml`/`triage.yml` chain directly)
against both real forks, with the template's `uses:` refs pointed at
`@vX.Y.Z`. This is the only gate that actually walks the cross-repo,
multi-hop `uses:` chain a real consumer's `cast.yml` walks - it's what would
have caught the annotated-tag bug that prompted this doc.

If both solvers complete a clean build -> fuzz -> triage cycle: the tag is
good - move on to gate 4.

If either fails: the tag was cut on a bad commit. Move it
(`git push origin :refs/tags/vX.Y.Z`, retag, re-push) or delete it and
restart from gate 1 - don't leave a published tag pointing at a commit that
failed its own release gate.

## 4. File the GitHub Release

Only once gate 3 has passed for both solvers:

```
gh release create vX.Y.Z --title vX.Y.Z --notes "..."
```

This is the step that actually makes `vX.Y.Z` a release rather than just a
tag that happened to pass its checks - it's the public signal to consumers
that it's safe to bump their `cast.yml` refs to it, and it's where the
release description belongs (see gate 2 - never in the tag message). Notes
should summarize what changed since the previous release; the closed
issues under that version's label (e.g. `v0.2.0`) are the source for that.

## v1.0.0 prerequisites

The four gates above apply to every release and are necessary but not
sufficient for v1.0.0 specifically. Before cutting v1.0.0, all three of the
following must also hold:

- **5 real bugs, across at least 2 different solvers.** Genuinely new,
  triage-discovered-and-filed bugs - not the two pinned gate-1 fixtures
  (z3 `0bd679a`, cvc5 `be30d27`), which only prove detection still works on
  bugs already known. This proves the pipeline finds real, previously-unknown
  issues in the wild, on more than one solver.
- **Stable for a week.** The unattended production schedule (`manager`'s
  hourly tick, the 6-hourly `cycle`, `daily-check`) running clean across all
  solvers for 7 consecutive days with zero required operator intervention.
  None of gates 1-3 exercise this - they're either manually dispatched or a
  single cycle - so a week of real unattended scheduling is the only thing
  that would have caught something like the annotated-tag bug's ~10h outage
  before a human noticed it independently.
- **Intuitive UI (new structure).** CAST today is GitHub-Actions-only -
  `workflow_dispatch` inputs, Actions run logs, filed issues - with no
  dedicated interface. v1.0.0 needs a real UI, not just YAML/CLI. Closest
  existing tracked work: #70 ("Build a dashboard of fuzzing status across
  all CAST users"), currently `backlog` and framed narrower (a status
  dashboard) than the full restructure this implies - needs rescoping, not
  just relabeling, before it counts toward this.

## What each gate does *not* catch

- Gate 1 (`pre-release.yml`) never builds from source, never fuzzes, never
  files a report, and only knows about two hardcoded (commit, bug) pairs -
  it says nothing about a new bug class, a new solver, or whether the
  solver still compiles.
- Gate 3 (full cycle) is the expensive one (~6h per solver) - only run it
  once gate 1 is already green, not as a substitute for it.
- Neither gate is wired into git itself - nothing blocks a tag from being
  pushed without either check having run. This is a checklist, not an
  enforced CI gate.
