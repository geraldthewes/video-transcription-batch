# Video Transcription Batch Processing

A cloud-native containerized service for batch transcription of YouTube videos using Multi-Step Transcriber (MST). Designed for deployment in orchestrators like Nomad and Kubernetes with simplified S3-based job management.

## Overview

This service processes batches of YouTube videos with high-quality transcription including speaker diarization and topic segmentation. Version 4.0.0 introduces a major simplification with unified S3 paths and environment-based configuration for easier deployment and management.

## Key Features

- **🎥 Batch Processing**: Process multiple YouTube videos sequentially
- **🎤 High-Quality Transcription**: MST with Whisper, LLM correction, and speaker diarization
- **☁️ S3 Integration**: Automatic upload/download of videos and transcripts
- **🔄 Idempotent Operations**: Skip already processed videos for reliability
- **📊 Progress Tracking**: Real-time progress monitoring and comprehensive logging
- **🛡️ Error Handling**: Robust retry logic and detailed error reporting
- **🚀 GPU Acceleration**: CUDA support for efficient model inference
- **🏗️ Cloud-Native**: Zero-volume deployment ready for orchestrators

## Architecture

### Components

- **Docker Container**: Transcription service with CUDA/AI libraries
- **Python Client Package**: Job management utilities and API clients
- **CLI Tools**: Batch job management and Nomad integration utilities

## Configuration

### Environment Configuration (.env file)

Version 4.0.0 uses a simplified `.env` file approach:

```bash
# Copy template and customize
cp env-template .env
```

**Required Configuration:**
```bash
# S3 Configuration
S3_TRANSCRIBER_BUCKET=my-transcriber-bucket
S3_TRANSCRIBER_PREFIX=jobs
AWS_REGION=us-east-1

# Service URLs
OLLAMA_URL=http://ollama.service.consul:11434
```

**Optional Configuration:**
```bash
# Custom S3 endpoint
S3_ENDPOINT_URL=https://s3.custom.com

# Deployment Configuration
NOMAD_ADDR=http://nomad.service.consul:4646
VAULT_ADDR=https://vault.service.consul:8200
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

### S3 Structure

Each job is organized under a UUID-based directory:
```
s3://transcriber-bucket/prefix/job-uuid/
├── tasks.json          # Video tasks to process
├── config.json         # Transcription parameters
├── results.json        # Processing results  
├── inputs/             # Downloaded videos
└── outputs/            # Generated transcripts
```

## Quick Start

```bash
# 1. Install the client tools
pip install -e .

# 2. Setup environment configuration
cp env-template .env
# Edit .env with your AWS and service configuration

# 3. Create tasks file
python -m scripts.batch_transcribe create-task --output my-videos.json

# 4. Upload tasks with transcription parameters
python -m scripts.batch_transcribe upload my-videos.json \
  --whisper-model whisper-turbo \
  --speaker-diarization \
  --min-segment-size 5 \
  --generate-env

# 5. Run container with simplified environment
docker run --gpus all \
  -e S3_TRANSCRIBER_BUCKET=my-transcriber \
  -e S3_TRANSCRIBER_PREFIX=jobs \
  -e S3_JOB_ID=abc-123-def \
  -e AWS_ACCESS_KEY_ID=xxx \
  -e AWS_SECRET_ACCESS_KEY=xxx \
  -e OLLAMA_URL=http://ollama:11434 \
  registry.cluster:5000/video-transcription-batch:v4.0.0
```

## CLI Utilities

### batch-transcribe

Manage S3-based batch transcription jobs with environment-based configuration:

```bash
# Setup environment
cp env-template .env && nano .env

# Create tasks file (generates UUID-based filename)
python -m scripts.batch_transcribe create-task

# Upload tasks with transcription parameters
python -m scripts.batch_transcribe upload my-videos.json \
  --whisper-model whisper-turbo \
  --speaker-diarization \
  --min-segment-size 5 \
  --generate-env \
  --ollama-url http://ollama.service.consul:11434

# Check job status
python -m scripts.batch_transcribe status abc-123-def

# View transcription configuration
python -m scripts.batch_transcribe config abc-123-def

# List all jobs
python -m scripts.batch_transcribe list

# Download results
python -m scripts.batch_transcribe download abc-123-def --output results.json
```

### generate-nomad-job

Create Nomad HCL job specifications:

```bash
generate-nomad-job \
  --job-id my-job-123 \
  --job-name video-transcription-my-job \
  --video-bucket my-videos \
  --output-bucket my-transcripts \
  --ollama-url http://ollama.service.consul:11434 \
  --docker-image registry.cluster:5000/video-transcription-batch:latest
```

This generates a complete Nomad job spec with Vault integration for secrets.

## Nomad Deployment

### Example Nomad Job (v4.0.0)

```hcl
job "video-transcription" {
  datacenters = ["dc1"]
  type        = "batch"

  vault {
    policies = ["transcription-policy"]
  }

  group "transcriber" {
    count = 1

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
        cpu    = 2000
        memory = 4096
        
        device "nvidia/gpu" {
          count = 1
        }
      }
    }
  }
}
```

## Python API

Use the S3BatchManager programmatically with v4.0.0:

```python
from transcription_client import S3BatchManager

# Initialize manager (uses environment variables from .env)
manager = S3BatchManager(
    transcriber_bucket='my-transcriber-bucket',
    transcriber_prefix='jobs'
)

# Upload tasks with transcription configuration
tasks = [
    {
        "url": "https://youtu.be/VlaGzSLsJ_0",
        "title": "Example Video",
        "description": "Example description"
    }
]
job_id = manager.upload_tasks(
    tasks,
    transcription_config={
        'whisper_model': 'whisper-turbo',
        'speaker_diarization': True,
        'min_segment_size': 5
    }
)

# Check status
status = manager.get_job_status(job_id)
print(f"Progress: {status['progress']:.1%}")

# Download results and config when complete
if status['status'] == 'completed':
    results = manager.download_results(job_id)
    config = manager.download_config(job_id)
```

## File Formats

### Tasks Format (tasks.json)

```json
[
  {
    "url": "https://youtu.be/VIDEO_ID",
    "title": "Video Title",
    "published_at": "2025-08-20T22:53:57Z",
    "description": "Video description (optional)"
  }
]
```

### Results Format (results.json)

```json
[
  {
    "url": "https://youtu.be/VIDEO_ID",
    "title": "Video Title",
    "video_id": "VIDEO_ID",
    "channel": "Channel Name",
    "status": "success|failed|skipped|processing",
    "error": "Error details if failed",
    "processed_at": "2025-08-21T12:00:00Z"
  }
]
```

## Output Structure

### S3 Storage Layout (v4.0.0)

**Job Directory:**
```
s3://transcriber-bucket/prefix/job-uuid/
├── tasks.json          # Input video tasks
├── config.json         # Transcription parameters  
├── results.json        # Processing results
├── inputs/             # Downloaded videos
│   └── {channel}/{video_id}/{video_id}.mp4
└── outputs/            # Generated transcripts
    └── {channel}/{video_id}/
        ├── {video_id}_transcript.md
        └── {video_id}_transcript.json
```

### Transcript Formats

**Markdown**: Human-readable with speaker labels, timestamps, and topics  
**JSON**: Structured data with segments, speakers, and metadata

## Error Handling

- **Retry Logic**: 3 attempts for downloads and audio extraction
- **Idempotency**: Skips already processed videos
- **Graceful Failures**: Individual video failures don't stop batch processing
- **Comprehensive Logging**: Detailed error information for debugging

## Development

### Building

The container is built automatically using the Nomad MCP Builder service:

```bash
# Trigger build (handled automatically on git push)
# Latest build: registry.cluster:5000/video-transcription-batch:v4.0.0
```

### Local Development

```bash
# Install client package
pip install -e .

# Run tests
pytest

# Build locally (if needed)
docker build -f docker/Dockerfile -t video-transcription-batch .
```


## Support

- **Documentation**: See CLAUDE.md for detailed technical information
- **Issues**: Check logs and environment variables first
- **Common Problems**: Network connectivity, credentials, GPU availability

## License

MIT License. This project integrates with Multi-Step Transcriber - refer to individual dependency licenses.