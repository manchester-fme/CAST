
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

Two independent sections - fill in whichever pipeline(s) you want.

- Write `list_tests_command`/`run_test_command` to run with your solver
  checked out as a directory literally named `<solver>`, one level above
  your cwd (e.g. `cd <solver>/build && ctest ...`).
- Set `target_jobs`/`avg_test_time_seconds` to size the parallel
  coverage-mapping jobs - a rough time estimate is fine.

```jsonc
{
  "coverage": {
    "repo_url": "<GITHUB-REPO>",
    "list_tests_command": "<prints one test name per line>",
    "run_test_command": "<runs one test; {test} is substituted in; exit 0 = passed>",
    "target_jobs": 4,
    "avg_test_time_seconds": 10.0
  },
  "fuzzer": {
    "tests_root": "<PATH_TO_TESTS>",
    "target_binary_path": "<PATH_TO_SOLVER>",
    "oracle_solver": "<REFERENCE-SOLVER-NAME, e.g. z3>"
  }
}
```

### `.cast/build.sh`

Read `"$@"` and branch on these flags:

| Flags | What to build |
|---|---|
| _(none)_ | production build |
| `--static` | statically-linked production build |
| `--coverage` | debug build instrumented for gcov (compile/link with `--coverage`) + install `fastcov` |
| `--static --coverage` | both |

End with a runnable binary at the path given by `cast.yml`'s `binary_path`
input / the manifest's `fuzzer.target_binary_path`.

```bash
#!/bin/bash
set -e
COVERAGE=false; STATIC=false
for arg in "$@"; do
  case "$arg" in
    --coverage) COVERAGE=true ;;
    --static)   STATIC=true ;;
  esac
done

# ...clone/configure/build here, branching on $COVERAGE/$STATIC as needed
```

### `.github/workflows/cast.yml`

Set `repo_url` to your own fork (not upstream). Only change
`solver`/`repo_url`/`build_script`/`binary_path`/`solver_dir` per job below
- leave the schedule and job structure as-is.

Pin the `uses:` refs to a released CAST tag (e.g. `@v0.1.1`), not `@main` -
`@main` tracks CAST's active development branch, so a push to CAST could
silently change your pipeline's behavior underneath you. Bump the tag
deliberately when you want to pick up a new CAST release.

(Maintainers: see [docs/release.md](docs/release.md) for the full
release procedure. Short version: cut release tags as lightweight
(`git tag vX.Y.Z <sha>`, no `-a`/`-m`), and put the release description
in a GitHub Release instead of the tag message. Annotated tags break
nested reusable-workflow calls that resolve relative to them, e.g.
`coverage-daily-check.yml`'s call to `./coverage-mapper.yml` - see
https://github.com/orgs/community/discussions/55649.)

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
    uses: manchester-fme/CAST/.github/workflows/build.yml@v0.1.1
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
