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

## Roadmap to v1.0.0

Every 0.X release between now and v1.0.0 exists to close the gap on the
three prerequisites above, without regressing anything already shipped.
Concretely, every release should:

- **Pass all four gates unchanged.** Nothing about moving faster toward
  1.0 means skipping or weakening gates 1-3.
- **Clear its version label before tagging.** Every issue labeled `vX.Y.0`
  is closed or explicitly relabeled (to the next version, or `backlog`)
  before that tag is cut, so the label always reflects what shipped, not
  what was hoped for.
- **Not regress the unattended schedule.** v0.9.0 (below) is where the
  7-consecutive-day stability clock formally starts, but every release
  before it should still treat "did this break `manager`'s hourly tick,
  the 6-hourly `cycle`, or `daily-check`" as an implicit gate - the whole
  point of hardening the scheduler in v0.4.0 is wasted if something after
  it reintroduces a regression that only gets caught once v0.9.0 starts
  the clock for real.
- **State its progress against the three prerequisites in the release
  notes** - bug tally, stability-streak status, UI status - the way
  v0.2.1's notes already did informally for bugs.

Each release also has its own theme - the reason its issues are grouped
together, not just "whatever was next in the backlog":

### v0.3.0 - repo hygiene
Minimize what CAST leaves behind in a client's solver repo, before
onboarding more solvers depends on that footprint being trustworthy.
- #74 Client repos should be stripped to minimum

### v0.4.0 - harden the interfaces
Close the gaps in CAST's own reliability and config surface that would
otherwise undermine both the stability clock (v0.9.0) and the ongoing
bug-finding credibility toward the 5-bugs/2-solvers bar - fix drift-prone
hardcoding, document what's actually supported, and stop triage/the
manager from cutting corners before either becomes a metric that's being
watched.
- #76 Hardcoding: solver invocation flags duplicated in three places with
  no sync check
- #75 Accumulating backlog of manager actions when CAST cycle is running
- #67 Harden duplicate-issue detection in triage reporting
- #66 Improve the solver-facing config surface (manifest.json / fuzzing
  controls)
- #65 Improve README / setup documentation clarity
- #71 Clarify and document the set of repos CAST is intended to work with

### v0.5.0 - architectural change
Give CAST a real interface beyond GitHub Actions logs - `workflow_dispatch`
inputs and Actions run logs replaced by a dedicated view of run status,
filed bugs, and fuzzing coverage. #78 is the actual UI restructure v1.0.0
needs - #70's narrower "status dashboard" no longer counts as this
release's deliverable, downgraded to a v0.6.0 follow-on once the
architecture it depends on exists.
- #78 Architectural change

### v0.6.0-v0.8.0 - iterate to close the gap
Whatever's left before the stability clock starts in v0.9.0: #70 (status
dashboard) built against the v0.5.0 architecture, #72 and #69 (both
currently `backlog`) if they end up feeding the UI's observability needs,
and triage continuing to accumulate confirmed bugs across solvers toward
the 5-bugs/2-solvers bar.

### v0.9.0 - stability
Run the unattended production schedule (`manager`'s hourly tick, the
6-hourly `cycle`, `daily-check`) clean across all solvers for 7
consecutive days with zero required operator intervention. Any
intervention needed during the window is a bug: fix it and restart the
clock, don't just note it and move on - this release doesn't ship until
the streak completes clean.

### v1.0.0
Cut once, at the same time: 5 real bugs across >=2 solvers, the v0.9.0
stability streak completed clean, and the UI from v0.5.0-v0.8.0 shipped -
not before.

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
