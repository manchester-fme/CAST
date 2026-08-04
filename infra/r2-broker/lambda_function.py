"""R2 storage broker Lambda.

Sits behind a Lambda Function URL with AuthType=AWS_IAM. AWS itself verifies
the caller's SigV4-signed request (rejecting anything invalid before this
code even runs) - this function does no authentication of its own. Its only
job: figure out which repo is calling (from the IAM-authenticated assumed
role's session name), and hand back a short-lived R2 presigned URL for the
requested operation. The actual object bytes then flow directly between the
caller and R2 - this Lambda never reads or writes object data itself, so
there is no AWS data-transfer cost regardless of object size.

Reads (get/head/list) are unrestricted - callers need to read unnamespaced
canonical production data too (e.g. a fork fuzzing cvc5 reads the real
upstream z3 oracle build at solvers/z3/..., not anything under its own
namespace). Writes (put/delete) are strictly scoped to the caller's own
namespace prefix - that's the actual tenant-isolation boundary enforced
here: nobody can corrupt another caller's, or the real production's, state.

Counterpart on the caller side: src/util/r2_broker_client.py. The two must
agree on the session-name <-> namespace mapping (see _namespace_from_session
below) and on the request/response JSON shape.

Required environment variables (set on the Lambda, never exposed to callers):
  R2_ACCOUNT_ID       Cloudflare account ID (used to build the R2 endpoint URL)
  R2_ACCESS_KEY_ID    R2 API token access key
  R2_SECRET_ACCESS_KEY R2 API token secret
  R2_BUCKET_NAME      Target bucket name
"""

import json
import os

import boto3

PRESIGN_EXPIRES_IN = 300  # seconds
SUPPORTED_OPERATIONS = {'get_object', 'put_object', 'head_object', 'delete_object', 'list_objects_v2'}


def _r2_client():
    account_id = os.environ['R2_ACCOUNT_ID']
    return boto3.client(
        's3',
        endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        region_name='auto',
    )


def _namespace_from_session(session_name: str) -> str:
    """Reverses the sanitization the Python client applies to github.repository
    ("owner/repo") before using it as an IAM role session name (which cannot
    contain "/"). "@" is used as the separator since it's allowed in IAM
    session names but never appears in a GitHub owner or repo name."""
    return session_name.replace('@', '/', 1)


def _caller_namespace(event: dict) -> str:
    iam = event.get('requestContext', {}).get('authorizer', {}).get('iam', {})
    user_arn = iam.get('userArn', '')
    # Assumed-role ARN shape: arn:aws:sts::<account>:assumed-role/<role-name>/<session-name>
    session_name = user_arn.rsplit('/', 1)[-1] if '/' in user_arn else ''
    if not session_name:
        raise PermissionError(f"Could not determine caller identity from userArn: {user_arn!r}")
    return _namespace_from_session(session_name)


def _response(status_code: int, body: dict) -> dict:
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(body),
    }


def handler(event, context):
    try:
        namespace = _caller_namespace(event)
    except PermissionError as e:
        return _response(403, {'error': str(e)})

    try:
        payload = json.loads(event.get('body') or '{}')
    except json.JSONDecodeError:
        return _response(400, {'error': 'Request body must be JSON'})

    operation = payload.get('operation')
    if operation not in SUPPORTED_OPERATIONS:
        return _response(400, {'error': f'operation must be one of {sorted(SUPPORTED_OPERATIONS)}'})

    key_field = 'prefix' if operation == 'list_objects_v2' else 'key'
    target = payload.get(key_field)
    if not target:
        return _response(400, {'error': f'"{key_field}" is required for operation {operation}'})

    # Reads are unrestricted - callers need to read unnamespaced canonical
    # production data too (e.g. a fork fuzzing cvc5 reads the real upstream
    # z3 oracle build at solvers/z3/..., not anything under its own
    # namespace). Writes are strictly scoped to the caller's own namespace -
    # this is the actual tenant-isolation boundary: nobody can corrupt
    # another caller's (or the real production's) state.
    if operation in ('put_object', 'delete_object'):
        allowed_prefix = f'{namespace}/'
        if not target.startswith(allowed_prefix):
            return _response(403, {'error': f'{key_field} must be under "{allowed_prefix}" for this caller'})

    bucket = os.environ['R2_BUCKET_NAME']
    client = _r2_client()

    params = {'Bucket': bucket}
    params['Prefix' if operation == 'list_objects_v2' else 'Key'] = target

    try:
        url = client.generate_presigned_url(
            ClientMethod=operation,
            Params=params,
            ExpiresIn=PRESIGN_EXPIRES_IN,
        )
    except Exception as e:
        return _response(500, {'error': f'Failed to generate presigned URL: {e}'})

    return _response(200, {'url': url, 'expires_in': PRESIGN_EXPIRES_IN})
