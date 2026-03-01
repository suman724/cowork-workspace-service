# cowork-workspace-service

Workspace and artifact storage service for the cowork platform. Manages workspace lifecycle (create, list, delete) and artifact content storage (DynamoDB metadata + S3 content).

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/workspaces` | Create or resolve a workspace |
| GET | `/workspaces?tenantId=...&userId=...` | List workspaces |
| GET | `/workspaces/{id}` | Get workspace details |
| DELETE | `/workspaces/{id}` | Delete workspace (cascades artifacts) |
| POST | `/workspaces/{id}/artifacts` | Upload an artifact |
| GET | `/workspaces/{id}/artifacts/{artifactId}` | Download artifact content |
| GET | `/workspaces/{id}/artifacts` | List artifacts |
| GET | `/health` | Liveness check |
| GET | `/ready` | Readiness check |

## Development

```bash
# Install dependencies (requires cowork-platform sibling repo)
make install

# Run all checks
make check

# Run with uvicorn
uvicorn workspace_service.main:app --reload

# Run tests with coverage
make coverage

# Build Docker image
make docker-build
```

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `ENV` | `dev` | Environment name |
| `LOG_LEVEL` | `info` | Logging level |
| `AWS_REGION` | `us-east-1` | AWS region |
| `AWS_ENDPOINT_URL` | — | Override for LocalStack/DynamoDB Local |
| `DYNAMODB_TABLE_PREFIX` | `dev-` | Table name prefix |
| `S3_BUCKET` | `dev-workspace-artifacts` | S3 bucket for artifact content |
| `MAX_ARTIFACT_SIZE_BYTES` | `52428800` | Max artifact size (50 MB) |

## Workspace Resolution

- **local** scope: Idempotent by `{tenantId}#{userId}#{localPath}` via GSI. Returns existing workspace if found.
- **general** scope: Always creates a new workspace.
- **cloud** scope: Phase 3+.

## Artifact Storage

- Metadata stored in DynamoDB (`{env}-artifacts` table)
- Content stored in S3 (`{env}-workspace-artifacts` bucket)
- Session history uses overwrite semantics (old snapshot deleted on new upload)
- Workspace deletion cascades: artifact metadata + S3 content + workspace record
