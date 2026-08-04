# r2-broker deployment

Lets any GitHub Actions run — including forks CAST doesn't control — read
and write CAST's R2 bucket without ever holding a static credential. See
the module docstrings in `lambda_function.py` and
`../../src/util/r2_broker_client.py` for the full design rationale; this
file is just the setup steps.

Nothing here is CAST-repo config — it's all AWS/Cloudflare account setup,
done once by whoever owns the storage.

## 1. Create an R2 API token

Cloudflare dashboard → R2 → Manage R2 API Tokens → Create API Token.
Scope it to the specific bucket, "Object Read & Write" permission. Note the
Access Key ID and Secret Access Key — these go on the Lambda only (step 4),
never anywhere a caller can see them.

## 2. Create the GitHub OIDC identity provider (one-time, skip if you already have one)

AWS Console → IAM → Identity providers → Add provider:
- Provider type: OpenID Connect
- Provider URL: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`

## 3. Create the IAM role

Trust policy (who can assume it — `repo:*:*` trusts any repo on GitHub,
since "anyone can bring their own compute" is the point; tighten the
`StringLike` condition to specific orgs/repos if you want an allowlist
instead):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:*:*"
        }
      }
    }
  ]
}
```

Permission policy (what it's allowed to do — just invoke the one Lambda
you'll create in step 4; replace `<ACCOUNT_ID>`/`<REGION>` once known):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "lambda:InvokeFunctionUrl",
      "Resource": "arn:aws:lambda:<REGION>:<ACCOUNT_ID>:function:cast-r2-broker"
    }
  ]
}
```

Note the role's ARN once created — this is `R2_BROKER_ROLE_ARN` (step 6).
It is **not** a secret; the trust policy above is what actually gates
access, not knowledge of the ARN.

## 4. Create the Lambda

- Runtime: Python 3.12 (boto3 ships with the runtime — no layers, no
  dependencies to package).
- Paste in `lambda_function.py` from this directory as-is (handler:
  `lambda_function.handler`).
- Environment variables:
  - `R2_ACCOUNT_ID` — your Cloudflare account ID
  - `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` — from step 1
  - `R2_BUCKET_NAME` — the target bucket

## 5. Enable a Function URL

Lambda console → Configuration → Function URL → Create:
- Auth type: **AWS_IAM** (this is what makes AWS verify every request
  before your code runs at all — do not use NONE)

Note the Function URL — this is `R2_BROKER_FUNCTION_URL` (step 6). Also not
a secret, for the same reason as the role ARN.

## 6. Wire the values into CAST's workflows

In each of `build.yml`, `manager.yml`, `coverage-mapper.yml`,
`coverage-daily-check.yml`, `commit-fuzzer.yml`, replace the two
`REPLACE-ME` placeholders in every `Configure storage backend` step:

```yaml
r2_broker_function_url: 'https://REPLACE-ME.lambda-url.us-east-1.on.aws/'
r2_broker_role_arn: 'arn:aws:iam::REPLACE-ME:role/cast-r2-broker'
```

A one-line find/replace across the five files is enough — the values are
identical everywhere.

## 7. Try it

From any repo (a real fork works, but so does a scratch repo — the broker
doesn't care who's asking beyond the trust policy), add a workflow with
`permissions: id-token: write` that calls one of CAST's reusable workflows
with `solver`/`repo_url` set, and set `vars.AWS_STORAGE_PROVIDER` to
`r2-broker` in that repo's own Settings → Variables (this is the one
caller-side choice that can't be baked into CAST's workflows, since CAST's
own production runs still need `aws`/`r2` with static keys). Watch the run:
- `Configure storage backend` should succeed with no AWS/R2 secrets set in
  the calling repo at all.
- Any step that reads/writes state (build-queue, coverage-mapper output,
  fuzzer bugs) should succeed via a presigned URL — check the run logs for
  `r2-broker request failed` if something's misconfigured, which will name
  the actual HTTP status/error from the Lambda.
- Try a **write** to a key that doesn't start with that repo's own
  `<owner>/<repo>/` namespace (there's no easy way to trigger this from the
  normal pipeline — it's the thing to keep in mind if you ever extend the
  workflows) - it should come back `403` from the Lambda, confirming the
  per-caller write scoping actually holds.
