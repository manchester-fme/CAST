# CAST 

Commit-Aware Solver Testing (CAST) continuously tests your SMT solver: every new 
commit gets built, fuzzed against a reference solver (e.g., cvc5) to catch bugs.

## Setup

Add three files to your solver's repo:

```
.cast/manifest.json           # test locations, build info, reference solver
.cast/build.sh                # your build script
.github/workflows/cast.yml    # triggers CAST's workflows on a schedule
```

Templates for all three are in [`example/`](example/); `manchester-fme/cvc5`
is a real, working reference.

## Fuzzing options
- **Coverage-guided** (default) — only fuzz the tests relevant to what a
  commit actually changed
- **`no_coverage`** — fuzz the whole test suite instead, no coverage
  mapping needed first (useful before any coverage data exists yet)
