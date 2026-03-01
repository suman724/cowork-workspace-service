"""S3-backed artifact content store."""

from __future__ import annotations

import io
from typing import Any

import structlog

logger = structlog.get_logger()


class S3ArtifactStore:
    """Upload/download/delete artifact content in S3."""

    def __init__(self, s3_client: Any, bucket: str) -> None:
        self._s3 = s3_client
        self._bucket = bucket

    async def upload(self, s3_key: str, content: bytes, content_type: str) -> None:
        await self._s3.upload_fileobj(
            io.BytesIO(content),
            self._bucket,
            s3_key,
            ExtraArgs={"ContentType": content_type},
        )
        logger.info("s3_upload", bucket=self._bucket, key=s3_key, size=len(content))

    async def download(self, s3_key: str) -> bytes:
        buf = io.BytesIO()
        await self._s3.download_fileobj(self._bucket, s3_key, buf)
        buf.seek(0)
        return buf.read()

    async def delete(self, s3_key: str) -> None:
        await self._s3.delete_object(Bucket=self._bucket, Key=s3_key)
        logger.info("s3_delete", bucket=self._bucket, key=s3_key)

    async def delete_prefix(self, prefix: str) -> None:
        paginator = self._s3.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                await self._s3.delete_object(Bucket=self._bucket, Key=obj["Key"])
        logger.info("s3_delete_prefix", bucket=self._bucket, prefix=prefix)
