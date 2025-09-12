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
✅ **Last Successful Build**: Job `71487294-1af4-416e-8bf0-febf3133af43` completed successfully on 2025-09-12
- All 15 Docker build steps completed
- Image successfully tagged as `latest` and `v1.0.0`
- Published to `registry.cluster:5000`

### Container Contents
The built container includes:
- Ubuntu 24.04 base with CUDA 12.8
- PyTorch with GPU support
- WhisperX and custom transcription libraries
- FFmpeg for audio/video processing
- Multi-step transcriber dependencies

## Python Client Package
The `transcription_client` package provides:
- `TranscriptionClient`: Main client class for API interactions
- Job management (submit, monitor, retrieve results)
- Data models for jobs and results
- Utility functions for video processing

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