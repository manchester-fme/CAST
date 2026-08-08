
<img height="300" alt="image" src="https://github.com/user-attachments/assets/6d6f248f-5b43-4bd4-9d4f-50a0ea8a5d0e" />

<p align="center">  
  <a href="https://github.com/manchester-fme/CAST/actions/workflows/ci.yml"><img src="https://github.com/manchester-fme/CAST/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License: Apache 2.0"></a>
</p>

## CAST
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
