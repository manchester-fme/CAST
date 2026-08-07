# Example CAST setup

Copy these three files into your solver's own repository, keeping the same
relative paths:

```
.cast/manifest.json
.cast/build.sh
.github/workflows/cast.yml
```

Then replace every `YOUR_SOLVER`/`YOUR_ORG` placeholder (plain text in
`build.sh`/`cast.yml`, angle-bracketed `<...>` descriptions in
`manifest.json`) with your own values. `manchester-fme/cvc5` is a real,
fully filled-in reference if you want to see what a finished setup looks
like.

## `manifest.json`

Two independent sections - fill in whichever pipelines you want:

- **`coverage`** - how to build/list/run your tests for coverage mapping.
  `list_tests_command` and `run_test_command` are shell commands CAST runs
  generically; `run_test_command` gets a literal `{test}` substituted in
  for each test. Leave `oracle_solver`/`oracle_fetch` as `null` unless your
  coverage tests themselves need a reference solver (rare).
- **`fuzzer`** - how to build/list your seed tests and which solver to
  diff against for differential fuzzing. `oracle_solver` is the reference
  solver's name; `oracle_fetch_fallback` says how to install it (`pip` is
  the simplest option if it's on PyPI).

## `build.sh`

Must accept `--coverage`/`--static` flags (CAST calls it both ways) and
leave a binary at the path declared by `cast.yml`'s `binary_path` input.

## `cast.yml`

Only the `solver`/`repo_url`/`build_script`/`binary_path`/`solver_dir`
values need to change - everything else (the schedule, the job structure)
can stay as-is. Uncomment `no_coverage: true` in the `fuzz` job if you'd
rather fuzz your whole test suite than the coverage-selected subset.
