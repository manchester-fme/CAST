# CAST

[![CI](https://github.com/manchester-fme/CAST/actions/workflows/ci.yml/badge.svg)](https://github.com/manchester-fme/CAST/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

Commit-Aware Solver Testing (CAST) continuously tests your SMT solver: every new 
commit gets built, fuzzed against a reference solver (e.g., cvc5) to catch bugs.

## Setup

Add three files to your solver's repo:

```
.cast/manifest.json           # test locations, build info, reference solver
.cast/build.sh                # your build script
.github/workflows/cast.yml    # triggers CAST's workflows on a schedule
```

Templates for all three are in [`example/`](example/); See
[`manchester-fme/cvc5`](https://github.com/manchester-fme/cvc5) for a real,
working reference.

## Fuzzing options
- **Coverage-guided** (default) — only fuzz the tests relevant to what a
  commit actually changed
- **`no_coverage`** — fuzz the whole test suite instead, no coverage
  mapping needed first (useful before any coverage data exists yet)
