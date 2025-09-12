# Video Transcription Batch Processing

A cloud-native containerized service for batch transcription of YouTube videos using Multi-Step Transcriber (MST). Designed for deployment in orchestrators like Nomad and Kubernetes with S3-based job management.

## Overview

This service processes batches of YouTube videos with high-quality transcription including speaker diarization and topic segmentation. It supports both traditional file-based configuration (for local development) and modern S3-based configuration (for production orchestration).

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

### Two Configuration Modes

1. **Legacy Mode** (file-based): Mount 3 JSON files for local development
2. **S3 Mode** (environment-based): Use environment variables + S3 for production

### Components

- **Docker Container**: Transcription service with CUDA/AI libraries
- **Python Client Package**: Job management utilities and API clients
- **CLI Tools**: Batch job management and Nomad integration utilities

## Quick Start

### Option 1: S3 Mode (Recommended for Production)

```bash
# 1. Install the client tools
pip install -e .

# 2. Create example tasks
batch-transcribe create-example --output my-videos.json

# 3. Upload tasks to S3
batch-transcribe upload my-videos.json \
  --generate-env \
  --video-bucket my-videos \
  --output-bucket my-transcripts \
  --ollama-url http://ollama.service.consul:11434

# 4. Run container with environment variables
docker run --gpus all \
  -e USE_S3_CONFIG=true \
  -e S3_TASKS_BUCKET=my-tasks \
  -e S3_TASKS_KEY=jobs/abc-123/tasks.json \
  -e S3_RESULTS_BUCKET=my-tasks \
  -e S3_RESULTS_KEY=jobs/abc-123/results.json \
  -e AWS_ACCESS_KEY_ID=xxx \
  -e AWS_SECRET_ACCESS_KEY=xxx \
  -e S3_VIDEO_BUCKET=my-videos \
  -e S3_OUTPUT_BUCKET=my-transcripts \
  -e OLLAMA_URL=http://ollama:11434 \
  -e SPEAKER_DIARIZATION=true \
  registry.cluster:5000/video-transcription-batch:latest
```

### Option 2: Legacy Mode (Local Development)

```bash
# 1. Prepare configuration files
cp config/config.example.json my-config.json
cp config/tasks.example.json my-tasks.json
# Edit files with your settings

# 2. Run container with volume mounts
docker run --gpus all \
  --env SPEAKER_DIARIZATION=true \
  -v $(pwd)/my-config.json:/app/config.json \
  -v $(pwd)/my-tasks.json:/app/tasks.json \
  -v $(pwd)/results.json:/app/results.json \
  registry.cluster:5000/video-transcription-batch:latest
```

## S3 Mode Configuration

### Environment Variables

**Core Configuration:**
- `USE_S3_CONFIG=true` - Enable S3 mode
- `S3_TASKS_BUCKET` - Bucket containing tasks.json
- `S3_TASKS_KEY` - S3 key for tasks.json (e.g., `jobs/abc-123/tasks.json`)
- `S3_RESULTS_BUCKET` - Bucket for results.json (defaults to tasks bucket)
- `S3_RESULTS_KEY` - S3 key for results.json (e.g., `jobs/abc-123/results.json`)

**AWS Configuration:**
- `AWS_ACCESS_KEY_ID` - AWS access key
- `AWS_SECRET_ACCESS_KEY` - AWS secret key
- `AWS_REGION` - AWS region (default: us-east-1)
- `S3_ENDPOINT` - Custom S3 endpoint (optional)

**Storage Configuration:**
- `S3_VIDEO_BUCKET` - Bucket for storing downloaded videos
- `S3_OUTPUT_BUCKET` - Bucket for storing transcription outputs
- `S3_PREFIX` - Optional prefix for S3 keys (default: processed/)

**MST Configuration:**
- `OLLAMA_URL` - Ollama service URL (required)
- `HF_TOKEN` - HuggingFace token (optional)
- `WHISPER_MODEL` - Whisper model (default: whisper-turbo)
- `LLM_MODEL` - LLM model (default: llama3)
- `EMBEDDING_MODEL` - Embedding model (default: nomic-embed-text)
- `MIN_SEGMENT_SIZE` - Minimum segment size (default: 5)

**Processing Options:**
- `SPEAKER_DIARIZATION` - Enable speaker diarization (default: true)
- `YT_DLP_FORMAT` - yt-dlp format string (default: best)

## CLI Utilities

### batch-transcribe

Manage S3-based batch transcription jobs:

```bash
# Create example tasks file
batch-transcribe create-example --output my-videos.json

# Upload tasks to S3
batch-transcribe upload my-videos.json \
  --job-id my-job-123 \
  --generate-env \
  --video-bucket my-videos \
  --output-bucket my-transcripts

# Check job status
batch-transcribe status my-job-123

# List all jobs
batch-transcribe list

# Download results
batch-transcribe download my-job-123 --output results.json
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

### Vault Integration

Store secrets in Vault:

```bash
# AWS credentials
vault kv put secret/nomad/jobs/aws-credentials \
  access_key_id="AKIA..." \
  secret_access_key="xxx"

# HuggingFace token
vault kv put secret/nomad/jobs/hf-token \
  token="hf_xxx"
```

### Example Nomad Job

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
        image = "registry.cluster:5000/video-transcription-batch:latest"
      }

      env {
        USE_S3_CONFIG       = "true"
        S3_TASKS_BUCKET     = "my-tasks"
        S3_TASKS_KEY        = "jobs/abc-123/tasks.json"
        S3_RESULTS_BUCKET   = "my-tasks"
        S3_RESULTS_KEY      = "jobs/abc-123/results.json"
        S3_VIDEO_BUCKET     = "my-videos"
        S3_OUTPUT_BUCKET    = "my-transcripts"
        OLLAMA_URL          = "http://ollama.service.consul:11434"
        SPEAKER_DIARIZATION = "true"
      }

      template {
        data = <<EOF
{{ with secret "secret/nomad/jobs/aws-credentials" }}
AWS_ACCESS_KEY_ID = "{{ .Data.data.access_key_id }}"
AWS_SECRET_ACCESS_KEY = "{{ .Data.data.secret_access_key }}"
{{ end }}
EOF
        destination = "secrets/aws.env"
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

Use the S3BatchManager programmatically:

```python
from transcription_client import S3BatchManager

# Initialize manager
manager = S3BatchManager(
    tasks_bucket='my-tasks',
    results_bucket='my-results'
)

# Upload tasks
tasks = [
    {
        "url": "https://youtu.be/VlaGzSLsJ_0",
        "title": "Example Video",
        "description": "Example description"
    }
]
job_id = manager.upload_tasks(tasks)

# Check status
status = manager.get_job_status(job_id)
print(f"Progress: {status['progress']:.1%}")

# Download results when complete
if status['status'] == 'completed':
    results = manager.download_results(job_id)
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

### S3 Storage Layout

**Videos:**
```
s3://{video_bucket}/{prefix}/{channel}/{video_id}/{video_id}.mp4
```

**Transcripts:**
```
s3://{output_bucket}/{prefix}/{channel}/{video_id}/{video_id}_transcript.md
s3://{output_bucket}/{prefix}/{channel}/{video_id}/{video_id}_transcript.json
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
# Latest build: registry.cluster:5000/video-transcription-batch:v2.0.0
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

## Migration from Legacy Mode

1. **Extract Configuration**: Convert config.json to environment variables
2. **Upload Tasks**: Use `batch-transcribe upload` to move tasks.json to S3
3. **Update Deployment**: Switch to S3 mode with `USE_S3_CONFIG=true`
4. **Remove Volumes**: No more volume mounts needed

## Support

- **Documentation**: See CLAUDE.md for detailed technical information
- **Issues**: Check logs and environment variables first
- **Common Problems**: Network connectivity, credentials, GPU availability

## License

MIT License. This project integrates with Multi-Step Transcriber - refer to individual dependency licenses.