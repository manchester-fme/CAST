
<p align="center">
  <img height="300" alt="image" src="https://github.com/user-attachments/assets/709b78d5-a4da-4158-adc4-0608c6ab8d1d" />
  <br/>
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

### `.cast/manifest.json`

Declares where your tests live, how to build/run them, and which solver to
diff against when fuzzing. Two independent sections - fill in whichever
pipeline(s) you want.

```jsonc
{
  "coverage": {
    "repo_url": "https://github.com/<org>/<solver>.git",
    "list_tests_command": "<prints one test name per line>",
    "run_test_command": "<runs one test; {test} is substituted in; exit 0 = passed>",
    "target_jobs": 4,
    "avg_test_time_seconds": 10.0,
    "oracle_solver": null
  },
  "fuzzer": {
    "tests_root": "<path to your seed corpus>",
    "target_binary_path": "./build/bin/<solver>",
    "oracle_solver": "<reference solver name, e.g. z3>",
    "oracle_fetch_fallback": { "type": "pip", "package": "z3-solver" }
  }
}
```

### `.cast/build.sh`

Builds your solver. CAST calls it with `--static` (production), `--coverage`
(instrumented), or both, and expects a runnable binary afterward at the path
declared by `cast.yml`'s `binary_path` input and the manifest's
`fuzzer.target_binary_path`.

```bash
#!/bin/bash
set -e
ENABLE_COVERAGE=false; ENABLE_STATIC=false
for arg in "$@"; do
  case "$arg" in
    --coverage) ENABLE_COVERAGE=true ;;
    --static)   ENABLE_STATIC=true ;;
  esac
done

git clone https://github.com/<org>/<solver>.git <solver> 2>/dev/null || true
cd <solver>

if [ "$ENABLE_COVERAGE" = true ]; then
  ./configure.sh debug --coverage
else
  ./configure.sh production ${ENABLE_STATIC:+--static}
fi
cd build && make -j"$(nproc)"
```

### `.github/workflows/cast.yml`

Wires CAST's reusable workflows (hosted in this repo) into your solver's own
schedule/manual dispatch. Only the `solver`/`repo_url`/`build_script`/
`binary_path`/`solver_dir` values need to change per job - the schedule and
job structure can stay as-is.

```yaml
on:
  workflow_dispatch:
    inputs:
      action: { type: choice, options: [manager, build, coverage, daily-check, fuzz] }
  schedule:
    - cron: '5,35 * * * *'   # build: build queued commits

jobs:
  build:
    if: inputs.action == 'build' || github.event.schedule == '5,35 * * * *'
    uses: manchester-fme/CAST/.github/workflows/build.yml@main
    with:
      solver: <solver>
      repo_url: ${{ github.server_url }}/${{ github.repository }}
      build_script: <solver>/.cast/build.sh
      binary_path: build/bin/<solver>
    secrets: inherit
  # ...manager/coverage/daily-check/fuzz jobs follow the same shape
```

## Fuzzing options
- **Coverage-guided** (default) — only fuzz the tests relevant to what a
  commit actually changed
- **`no_coverage`** — fuzz the whole test suite instead, no coverage
  mapping needed first (useful before any coverage data exists yet)
