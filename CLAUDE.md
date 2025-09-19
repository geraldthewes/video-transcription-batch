# Video Transcription Batch Project

## Overview
This project contains two main components:
1. **Docker Container**: A containerized environment for video transcription processing deployed to Nomad clusters
2. **Python Client Package**: A client library and CLI tools for interacting with the transcription containers

## Project Structure

```
video-transcription-batch/
├── docker/                    # Container build components
│   ├── Dockerfile            # Container definition with CUDA/AI libraries
│   ├── requirements.txt      # Python dependencies for container
│   └── app/
│       └── main.py          # Main transcription service
├── transcription_client/     # Python client package
│   ├── __init__.py          # Package initialization
│   ├── client.py            # API client for container interaction
│   ├── models.py            # Data models (jobs, results)
│   └── utils.py             # Utility functions
├── scripts/                  # Command-line scripts
│   └── yt-channel.py        # YouTube channel processing
├── config/                   # Configuration files
│   ├── config.example.json  # Configuration template
│   └── tasks.example.json   # Task configuration template
├── pyproject.toml           # Python package definition
└── CLAUDE.md               # This documentation
```

## Container Build
⚠️ **Important**: The Docker container should be built using the Nomad MCP build service, not locally on this machine.

### MCP Build Service
The project uses the [Nomad MCP Builder](https://github.com/geraldthewes/nomad-mcp-builder) service integrated via MCP:

**MCP Server Configuration:**
```bash
claude mcp add --transport http build-server https://10.0.1.12:31183/mcp
```

### Build Using MCP Tools

🚨 **CRITICAL WARNING: COMMIT FIRST!** 🚨
**The MCP build service clones from git - changes MUST be committed and pushed before building or builds will use old code!**

Use the MCP build service tools (available in Claude sessions after MCP server is added):

**Build Job Parameters:**
```json
{
  "repo_url": "https://github.com/geraldthewes/video-transcription-batch.git",
  "git_ref": "main",
  "dockerfile_path": "docker/Dockerfile",
  "image_name": "video-transcription-batch",
  "image_tags": ["latest", "v4.0.1"],
  "registry_url": "registry.cluster:5000",
  "owner": "gerald"
}
```

**⚠️ IMPORTANT**: Do NOT include `git_credentials_path` or `registry_credentials_path` parameters as they are not needed for this public repository and will cause build failures.

**Note**: The `dockerfile_path` is `"docker/Dockerfile"` due to the reorganized structure. The Dockerfile has been updated to use paths relative to the repository root (e.g., `COPY docker/requirements.txt /app/`). No `test_commands` are included initially.

### Build Features
- Three-phase pipeline: Build → Test → Publish
- WebSocket log streaming for real-time monitoring
- Integration with private registries (registry.cluster:5000)
- Rootless Buildah for secure builds

This is a large CUDA project, ensure the system is built, published and tested with sufficioent resources:
- Reserved CPU 4,000 MHz 
- Reserved Memory 8,192 MiB 
- Reserved Disk 20 Gb 


### Build Status
✅ **Latest Build**: Job `278de965-6153-4e0e-9008-c1363d612362` completed successfully on 2025-09-12 - v4.0.0
- **Major Refactor**: Unified S3 structure and environment-based configuration
- Simplified transcriber bucket with organized job directories
- Removed legacy video/output bucket separation
- Added config.json support for per-job transcription parameters
- Container environment variable simplification
- Image: `registry.cluster:5000/video-transcription-batch:v4.0.0`

✅ **Previous Builds**: 
- Job `399b9a73-084e-4352-a5d0-76ea9a8c7c83` (v3.0.0) - S3-only configuration
- Job `ae47464b-5c50-460f-b79f-357bcc6de589` (v2.0.0) - Added S3-based configuration  
- Job `71487294-1af4-416e-8bf0-febf3133af43` (v1.0.0) - Initial working version

### Container Contents
The built container includes:
- Ubuntu 24.04 base with CUDA 12.8
- PyTorch with GPU support
- WhisperX and custom transcription libraries
- FFmpeg for audio/video processing
- Multi-step transcriber dependencies

## Nomad Integration Example

```hcl
job "video-transcription" {
  datacenters = ["dc1"]
  type        = "batch"

  vault {
    policies = ["transcription-policy"]
  }

  group "transcriber" {
    task "main" {
      driver = "docker"
      config {
        image = "registry.cluster:5000/video-transcription-batch:v4.0.0"
      }

      env {
        S3_TRANSCRIBER_BUCKET = "transcription-jobs"
        S3_TRANSCRIBER_PREFIX = "jobs"
        S3_JOB_ID            = "${JOB_ID}"
        OLLAMA_URL           = "http://ollama.service.consul:11434"
        AWS_REGION           = "us-east-1"
      }

      template {
        data = <<EOF
{{ with secret "secret/aws/transcription" }}
AWS_ACCESS_KEY_ID="{{ .Data.data.access_key }}"
AWS_SECRET_ACCESS_KEY="{{ .Data.data.secret_key }}"
{{ end }}
{{ with secret "secret/hf/transcription" }}
HF_TOKEN="{{ .Data.data.token }}"
{{ end }}
EOF
        destination = "secrets/app.env"
        env         = true
      }

      resources {
        device "nvidia/gpu" { count = 1 }
        cpu    = 2000
        memory = 4096
      }
    }
  }
}
```

## Configuration

### Environment Configuration (.env file)

Version 4.0.0 uses a simplified `.env` file approach:

```bash
# Copy template and customize
cp env-template .env
```

**Required Configuration (.env):**
```bash
# AWS S3 Configuration (for client tools only)
S3_TRANSCRIBER_BUCKET=my-transcriber-bucket
S3_TRANSCRIBER_PREFIX=jobs
AWS_REGION=us-east-1

# Transcription Service URLs
OLLAMA_URL=http://ollama.service.consul:11434

# Optional: Deployment Configuration
S3_ENDPOINT_URL=https://s3.custom.com
NOMAD_ADDR=http://nomad.service.consul:4646
VAULT_ADDR=https://vault.service.consul:8200

# NOTE: Secrets (AWS credentials, HF tokens) are handled by Vault in production
```

### Vault Setup

Store secrets in Vault for secure deployment:

```bash
# AWS credentials for S3 access
vault kv put secret/aws/transcription \
  access_key="AKIA..." \
  secret_key="xxx..."

# Optional: HuggingFace token for model access
vault kv put secret/hf/transcription \
  token="hf_xxx..."
```

### S3 Path Structure

Each transcription job is organized under a UUID-based directory:
```
s3://<S3_TRANSCRIBER_BUCKET>/<S3_TRANSCRIBER_PREFIX>/<job-uuid>/
├── tasks.json          # Video tasks to process
├── config.json         # Transcription parameters (optional)
├── results.json        # Processing results
├── inputs/             # Downloaded video files
└── outputs/            # Generated transcripts and metadata
```

## Python Client Package
The `transcription_client` package provides:

### Core Classes
- `TranscriptionClient`: HTTP API client for transcription services (legacy)
- `S3BatchManager`: S3-based batch job management (v2.0.0+)
- Job management (submit, monitor, retrieve results)  
- Data models for jobs and results
- Utility functions for video processing

### S3BatchManager (v4.0.0+)
```python
from transcription_client import S3BatchManager

# Uses environment variables from .env file
manager = S3BatchManager(
    transcriber_bucket='my-transcriber-bucket',
    transcriber_prefix='jobs'
)

# Upload tasks with transcription config
job_id = manager.upload_tasks(
    video_tasks_list,
    transcription_config={
        'whisper_model': 'whisper-turbo',
        'speaker_diarization': True,
        'min_segment_size': 5
    }
)

# Monitor progress
status = manager.get_job_status(job_id)
print(f"Progress: {status['progress']:.1%}")

# Download results when complete
results = manager.download_results(job_id)
config = manager.download_config(job_id)
```

### Command-Line Tools

**batch-transcribe**: S3-based batch job management with environment-based configuration
```bash
# Setup: Copy and customize environment file
cp env-template .env
# Edit .env with your S3 and service configuration

# Create tasks file with random UUID filename
python -m scripts.batch_transcribe create-task

# Create tasks file with custom filename
python -m scripts.batch_transcribe create-task --output my-videos.json

# Upload tasks with transcription parameters
python -m scripts.batch_transcribe upload my-videos.json \
  --whisper-model whisper-turbo \
  --speaker-diarization \
  --min-segment-size 5 \
  --generate-env \
  --ollama-url http://ollama.service.consul:11434

# Check job status  
python -m scripts.batch_transcribe status abc-123-def

# View transcription configuration for a job
python -m scripts.batch_transcribe config abc-123-def

# List all jobs
python -m scripts.batch_transcribe list

# Download results
python -m scripts.batch_transcribe download abc-123-def --output results.json
```

**generate-nomad-job**: Generate Nomad HCL job specifications
```bash
generate-nomad-job \
  --job-id abc-123-def \
  --job-name video-transcription-batch \
  --video-bucket my-videos \
  --output-bucket my-transcripts \
  --ollama-url http://ollama.service.consul:11434
```

### Installation
```bash
pip install -e .
```

### Usage Example
```python
from transcription_client import TranscriptionClient

client = TranscriptionClient("http://transcription-service:8080")
job = client.submit_job("https://youtube.com/watch?v=example")
result = client.get_result(job.id)
```

## Scripts
- `yt-channel.py`: Extract video URLs from YouTube channels using the YouTube Data API

---

## Documentation Maintenance Guidelines

**IMPORTANT**: When making significant changes to this project:

### Documentation Synchronization
- **ALWAYS update both CLAUDE.md AND README.md** when making structural, configuration, or API changes
- README.md serves as the primary user-facing documentation and must stay in sync with CLAUDE.md
- Both files should accurately reflect the current version, capabilities, and usage patterns
- Version numbers, examples, and configuration instructions must be consistent across both files

### Commit Guidelines
- When committing changes that affect functionality, **ensure both documentation files are updated**
- Include documentation updates in the same commit or immediately follow up with a documentation commit
- Never leave documentation in an inconsistent state between files

### What Requires Documentation Updates
- Configuration structure changes (environment variables, S3 paths, etc.)
- CLI command changes (new commands, changed syntax, new parameters)
- API interface changes (new methods, changed signatures)
- Container environment variable changes
- Version updates and breaking changes
- New features or removed functionality

### Container Build Requirements

⚠️ **CRITICAL: COMMIT AND PUSH BEFORE BUILDING** ⚠️

**The MCP build service builds from the git repository, NOT from local files. All changes MUST be committed and pushed before triggering builds, or the build will use old versions of your files.**

**PRE-BUILD CHECKLIST:**
1. ✅ **COMMIT ALL CHANGES**: `git add .` and `git commit -m "..."`
2. ✅ **PUSH TO REMOTE**: `git push origin main`
3. ✅ **VERIFY PUSH**: Check that changes appear on GitHub
4. ✅ **THEN BUILD**: Use MCP build service

**Build When These Change:**
- **ALWAYS trigger a new container build** when making changes that affect the Docker container:
  - Changes to `docker/app/main.py` (container application code)
  - Changes to `docker/Dockerfile` or `docker/requirements.txt`
  - Environment variable handling changes in the container
  - New transcription configuration features
- **Monitor build progress** and update CLAUDE.md with successful build status
- Use the MCP build service to ensure consistency and proper tagging
- Update version references in documentation after successful builds

**Cache Issues:**
- Docker cache is extremely persistent across builds
- If changes don't appear, add cache-busting comments to Dockerfile
- Consider changing file content (not just comments) to force cache invalidation

This ensures users always have accurate, up-to-date information regardless of which documentation file they reference.
