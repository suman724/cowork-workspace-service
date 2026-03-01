"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    env: str = "dev"
    log_level: str = "info"
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None
    dynamodb_table_prefix: str = "dev-"
    s3_bucket: str = "dev-workspace-artifacts"
    max_artifact_size_bytes: int = 52428800  # 50 MB

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}

    @property
    def workspaces_table(self) -> str:
        return f"{self.dynamodb_table_prefix}workspaces"

    @property
    def artifacts_table(self) -> str:
        return f"{self.dynamodb_table_prefix}artifacts"
