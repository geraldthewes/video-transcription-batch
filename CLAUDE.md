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
⚠️ **Important**: The Docker container should be built using the MCP build service tool, not locally on this machine.

The container includes:
- Ubuntu 24.04 base with CUDA 12.8
- PyTorch with GPU support
- WhisperX and custom transcription libraries
- FFmpeg for audio/video processing

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