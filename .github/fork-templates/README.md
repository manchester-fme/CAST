# Building a fork from its own repo

`build-solver-fork.yml` (in `.github/workflows/`) is a solver-agnostic,
reusable workflow that builds one specific commit of cvc5 or Z3 from any git
URL - typically your own fork - and uploads the artifacts to the same S3
bucket the production pipeline uses, under a fork-specific prefix. It is
triggered directly from the forked repo's own Actions tab.

It does **not** replace or modify `cvc5-build.yml`, `z3-build.yml`,
`cvc5-manager.yml`, or `z3-manager.yml` - those keep polling the shared S3
build-queue for the official upstream repos exactly as before. Fork builds
are entirely separate and never write to that shared queue/fuzzing-schedule
state, so they can't collide with or corrupt production data.

## 1. Copy the caller workflow into your fork

Copy `build.yml` to `.github/workflows/` in your fork - the same, unmodified
file works for both a cvc5 fork and a Z3 fork. It detects which solver to
build from the repository name (the repo must contain "cvc5" or "z3" in its
name, which is true for a normal, unrenamed fork).

## 2. Add the required secrets to your fork

The caller workflow uses `secrets: inherit`, which forwards *your fork's own*
repository secrets to the reusable workflow - it does **not** pull secrets
from CAST. Add these secrets under your fork's
Settings -> Secrets and variables -> Actions (same values as CAST uses):

| Secret               | Required | Notes                              |
|----------------------|----------|-------------------------------------|
| `AWS_ACCESS_KEY_ID`     | yes | S3/R2 credentials with put-object access to the shared bucket |
| `AWS_SECRET_ACCESS_KEY` | yes | |
| `AWS_BUCKET_NAME`       | yes | |
| `AWS_REGION`            | no  | defaults to `eu-north-1` if unset |
| `AWS_ACCOUNT_ID`        | no  | only needed for the R2 provider |

Ask a CAST maintainer for scoped credentials rather than reusing
long-lived admin keys.

## 3. Run it

From your fork's Actions tab, run the workflow manually ("Run workflow").
Leave `ref` empty to build the branch/commit you dispatched from, or supply a
specific commit SHA. Check "coverage" to also produce a coverage-instrumented
build.

## Where artifacts land

Production builds (from `cvc5-build.yml`/`z3-build.yml`):

```
solvers/<solver>/builds/v2/production/<sha>.tar.gz
solvers/<solver>/builds/v2/coverage/<sha>.tar.gz
```

Fork builds (from this workflow):

```
solvers/<solver>/builds/v2/fork/<owner>/production/<sha>.tar.gz
solvers/<solver>/builds/v2/fork/<owner>/coverage/<sha>.tar.gz
```

where `<owner>` is derived from your fork's repo URL (e.g. the GitHub
username/org that owns it).
