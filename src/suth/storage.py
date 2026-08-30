import os
from pathlib import Path

import boto3
from botocore.client import Config


def get_bucket() -> tuple[object, str]:
    """Return (s3_client, bucket_name) from `specific dev`-injected env vars."""
    endpoint = os.environ["S3_ENDPOINT"]
    bucket = os.environ["S3_BUCKET"]
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        config=Config(s3={"addressing_style": "path"}),
        region_name="us-east-1",
    )
    return client, bucket


def upload_screenshot(local_path: str | Path, session_id: str) -> str:
    """Upload a locally-captured screenshot and return its storage key (ref)."""
    local_path = Path(local_path)
    key = f"sessions/{session_id}/{local_path.name}"
    client, bucket = get_bucket()
    client.upload_file(str(local_path), bucket, key)
    return key


def upload_video(local_path: str | Path, session_id: str) -> str:
    """Upload a session's finalized .webm recording and return its storage key."""
    local_path = Path(local_path)
    key = f"sessions/{session_id}/replay.webm"
    client, bucket = get_bucket()
    client.upload_file(str(local_path), bucket, key, ExtraArgs={"ContentType": "video/webm"})
    return key


def download_range(key: str, start: int, end: int) -> bytes:
    """Read a byte range [start, end] (inclusive) out of storage — backs the
    API's Range-request support for video scrubbing without downloading the
    whole file on every seek."""
    client, bucket = get_bucket()
    resp = client.get_object(Bucket=bucket, Key=key, Range=f"bytes={start}-{end}")
    return resp["Body"].read()


def object_size(key: str) -> int:
    client, bucket = get_bucket()
    return client.head_object(Bucket=bucket, Key=key)["ContentLength"]


def download_bytes(key: str) -> bytes:
    """Read an object back out of storage — used by the MCP screenshot resource."""
    client, bucket = get_bucket()
    return client.get_object(Bucket=bucket, Key=key)["Body"].read()


def delete_session_storage(session_ids: list[str]) -> None:
    """Remove replay videos and screenshots for the given sessions."""
    if not session_ids:
        return
    client, bucket = get_bucket()
    for session_id in session_ids:
        prefix = f"sessions/{session_id}/"
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            contents = page.get("Contents") or []
            if not contents:
                continue
            client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": obj["Key"]} for obj in contents]},
            )
