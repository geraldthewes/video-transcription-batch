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
Use the MCP build service tools (available in Claude sessions after MCP server is added):

**Build Job Parameters:**
```json
{
  "repo_url": "https://github.com/geraldthewes/video-transcription-batch.git",
  "git_ref": "main",
  "dockerfile_path": "docker/Dockerfile",
  "image_name": "video-transcription-batch", 
  "image_tags": ["latest", "v1.0.0"],
  "registry_url": "registry.cluster:5000",
  "owner": "gerald",
  "git_credentials_path": "secret/nomad/jobs/git-credentials",
  "registry_credentials_path": "secret/nomad/jobs/registry-credentials"
}
```

**Note**: The `dockerfile_path` is `"docker/Dockerfile"` due to the reorganized structure. The Dockerfile has been updated to use paths relative to the repository root (e.g., `COPY docker/requirements.txt /app/`). No `test_commands` are included initially.

### Build Features
- Three-phase pipeline: Build → Test → Publish
- WebSocket log streaming for real-time monitoring
- Integration with private registries (registry.cluster:5000)
- Rootless Buildah for secure builds

### Build Status
✅ **Latest Build**: Job `ae47464b-5c50-460f-b79f-357bcc6de589` completed successfully on 2025-09-12
- All 15 Docker build steps completed
- Image successfully tagged as `latest` and `v2.0.0` 
- Published to `registry.cluster:5000`
- **Major Update**: Added S3-based configuration support for cloud-native deployments

✅ **Previous Build**: Job `71487294-1af4-416e-8bf0-febf3133af43` (v1.0.0) - Initial working version

### Container Contents
The built container includes:
- Ubuntu 24.04 base with CUDA 12.8
- PyTorch with GPU support
- WhisperX and custom transcription libraries
- FFmpeg for audio/video processing
- Multi-step transcriber dependencies

## S3-Based Configuration (v2.0.0+)

### Overview
Version 2.0.0 introduces S3-based configuration for cloud-native deployments. This eliminates the need for volume mounts and enables seamless integration with orchestrators like Nomad and Kubernetes.

### Configuration Modes
The container supports two modes:

1. **Legacy Mode** (`USE_S3_CONFIG=false`, default for backward compatibility):
   - Requires 3 volume mounts: `/app/config.json`, `/app/tasks.json`, `/app/results.json`
   - Suitable for local development and testing

2. **S3 Mode** (`USE_S3_CONFIG=true`):
   - Zero volume mounts required
   - Configuration via environment variables
   - Tasks and results stored in S3
   - Ideal for production orchestrator deployments

### S3 Mode Environment Variables

**Core Configuration:**
```bash
USE_S3_CONFIG=true
S3_TASKS_BUCKET=my-tasks-bucket
S3_TASKS_KEY=jobs/abc-123/tasks.json
S3_RESULTS_BUCKET=my-results-bucket  # Optional, defaults to S3_TASKS_BUCKET
S3_RESULTS_KEY=jobs/abc-123/results.json
```

**AWS Configuration:**
```bash
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=xxx...
AWS_REGION=us-east-1
S3_ENDPOINT=https://s3.custom.com  # Optional for custom S3 endpoints
```

**Application Configuration:**
```bash
S3_VIDEO_BUCKET=my-videos-bucket
S3_OUTPUT_BUCKET=my-transcripts-bucket
S3_PREFIX=processed/
OLLAMA_URL=http://ollama.service.consul:11434
HF_TOKEN=hf_xxx...
WHISPER_MODEL=whisper-turbo
LLM_MODEL=llama3
EMBEDDING_MODEL=nomic-embed-text
MIN_SEGMENT_SIZE=5
SPEAKER_DIARIZATION=true
YT_DLP_FORMAT=best
```

### Nomad Integration Example

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
        image = "registry.cluster:5000/video-transcription-batch:v2.0.0"
      }

      env {
        USE_S3_CONFIG     = "true"
        S3_TASKS_BUCKET   = "transcription-jobs"
        S3_TASKS_KEY      = "jobs/${JOB_ID}/tasks.json"
        OLLAMA_URL        = "http://ollama.service.consul:11434"
        # ... other env vars
      }

      template {
        data = <<EOF
{{ with secret "secret/aws/transcription" }}
AWS_ACCESS_KEY_ID="{{ .Data.data.access_key }}"
AWS_SECRET_ACCESS_KEY="{{ .Data.data.secret_key }}"
{{ end }}
EOF
        destination = "secrets/aws.env"
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

## Python Client Package
The `transcription_client` package provides:

### Core Classes
- `TranscriptionClient`: HTTP API client for transcription services (legacy)
- `S3BatchManager`: S3-based batch job management (v2.0.0+)
- Job management (submit, monitor, retrieve results)  
- Data models for jobs and results
- Utility functions for video processing

### New S3BatchManager (v2.0.0+)
```python
from transcription_client import S3BatchManager

manager = S3BatchManager(
    tasks_bucket='my-tasks',
    results_bucket='my-results'
)

# Upload tasks and get job ID
job_id = manager.upload_tasks(video_tasks_list)

# Monitor progress
status = manager.get_job_status(job_id)
print(f"Progress: {status['progress']:.1%}")

# Download results when complete
results = manager.download_results(job_id)
```

### Command-Line Tools

**batch-transcribe**: S3-based batch job management
```bash
# Create example tasks
batch-transcribe create-example --output my-videos.json

# Upload tasks to S3
batch-transcribe upload my-videos.json --generate-env

# Check job status  
batch-transcribe status abc-123-def

# List all jobs
batch-transcribe list

# Download results
batch-transcribe download abc-123-def --output results.json
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

## Configuration
Copy example config files from `config/` directory and customize for your environment.