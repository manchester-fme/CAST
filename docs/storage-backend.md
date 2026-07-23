# Storage backend: AWS S3 / Cloudflare R2

State files, build artifacts, and coverage mappings are stored in an S3-compatible
bucket. The active backend is chosen by the `STORAGE_PROVIDER` repository variable:

- `r2` (or unset) — Cloudflare R2. This is the default.
- `aws` — AWS S3.

Because R2 implements the S3 API, no application logic changes between the two —
only credentials, bucket name, and endpoint URL differ.

## Switching backends

Set the repo/org variable `STORAGE_PROVIDER` to `r2` or `aws`
(Settings → Secrets and variables → Actions → Variables). This is a manual
toggle, not automatic failover — the two buckets are independent, so switching
mid-flight starts from whatever state already exists in the newly selected bucket.

## Required secrets

One unprefixed set of secrets serves both backends:

| Secret | Used by | Notes |
| --- | --- | --- |
| `BUCKET_NAME` | both | bucket name |
| `ACCESS_KEY_ID` | both | R2: generate under R2 → Manage API Tokens |
| `SECRET_ACCESS_KEY` | both | |
| `ACCOUNT_ID` | R2 only | builds `https://<account_id>.r2.cloudflarestorage.com` |
| `REGION` | AWS only | optional, defaults to `eu-north-1` |

Switching backends means repointing these same secrets, not maintaining two
parallel sets.

## How it works

- **Python (`src/storage_backend.py`)** — builds a boto3 client pointed at
  either backend. Used by `src/scheduling/s3_state.py` and
  `src/coverage/coverage_state.py`, so all state-file logic is unchanged.
- **CI (`.github/actions/configure-storage`)** — a composite action wrapping
  `src/configure_storage.sh`, invoked once per job as the "Configure storage
  backend" step. It exports `BUCKET_NAME`, `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, and (for R2) `AWS_ENDPOINT_URL_S3` into
  `$GITHUB_ENV`, so every later step — including raw `aws s3` / `aws s3api` CLI
  calls — automatically targets the right backend without any further changes.

## One-time R2 setup

1. Create the R2 bucket in the Cloudflare dashboard.
2. Generate an R2 API token (Account-scoped, read/write on that bucket) to get
   `ACCESS_KEY_ID` / `SECRET_ACCESS_KEY`.
3. Set `BUCKET_NAME`, `ACCOUNT_ID`, `ACCESS_KEY_ID`, `SECRET_ACCESS_KEY`
   and the `STORAGE_PROVIDER=r2` variable.
4. Optionally backfill existing state/build data from S3 to R2, e.g.:
   ```bash
   aws s3 sync s3://<aws-bucket> s3://<r2-bucket> \
     --endpoint-url https://<account_id>.r2.cloudflarestorage.com
   ```
   (uses AWS credentials for the source and picks up R2 credentials/endpoint
   for the destination via the standard AWS CLI profile/endpoint mechanism)
