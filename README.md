# YouTube Video Transcription Docker Service

A Dockerized Python service that automates the transcription of YouTube videos using the Multi-Step Transcriber (MST) library. This service processes batches of YouTube videos, downloads them, stores them in S3, extracts audio, performs high-quality transcription with speaker diarization and topic segmentation, and uploads structured outputs to S3.

## Features

- **Batch Processing**: Process multiple YouTube videos sequentially from a JSON task file
- **High-Quality Transcription**: Uses Multi-Step Transcriber (MST) with Whisper, LLM correction, and speaker diarization
- **S3 Integration**: Automatic upload/download of videos and transcription outputs
- **Idempotent Operations**: Skip already processed videos for reliability
- **Progress Tracking**: Real-time progress bars and comprehensive logging
- **Error Handling**: Robust retry logic and detailed error reporting
- **GPU Acceleration**: CUDA support for efficient model inference

## Prerequisites

- Docker with NVIDIA GPU support (`--gpus all`)
- External Ollama server running with required models
- S3 buckets with appropriate permissions
- YouTube videos that are publicly accessible

## Quick Start

### 1. Build the Docker Image

```bash
docker build -f Dockerfile.worker -t video-transcription-batch .
```

### 2. Prepare Configuration Files

Copy and customize the example files:

```bash
cp config.example.json config.json
cp tasks.example.json tasks.json
```

Edit `config.json` with your actual credentials and settings:

```json
{
  "s3": {
    "access_key": "YOUR_AWS_ACCESS_KEY",
    "secret_key": "YOUR_AWS_SECRET_KEY", 
    "region": "us-east-1",
    "video_bucket": "your-videos-bucket",
    "output_bucket": "your-transcripts-bucket",
    "prefix": "processed/",
    "endpoint": ""
  },
  "mst": {
    "hf_token": "YOUR_HUGGINGFACE_TOKEN",
    "ollama_url": "http://your-ollama-host:11434",
    "whisper_model": "whisper-turbo",
    "llm_model": "llama3",
    "embedding_model": "nomic-embed-text",
    "min_segment_size": 5
  },
  "download_options": {
    "yt_dlp_format": "best"
  }
}
```

Edit `tasks.json` with your YouTube videos:

```json
[
  {
    "url": "https://youtu.be/VIDEO_ID",
    "title": "Video Title",
    "published_at": "2025-08-20T22:53:57Z",
    "description": "Video description"
  }
]
```

### 3. Run the Service

```bash
docker run --gpus all \
  --env SPEAKER_DIARIZATION=true \
  -v $(pwd)/config.json:/app/config.json \
  -v $(pwd)/tasks.json:/app/tasks.json \
  -v $(pwd)/results.json:/app/results.json \
  video-transcription-service
```

## Configuration

### S3 Configuration

- `access_key`: AWS access key ID
- `secret_key`: AWS secret access key  
- `region`: AWS region (e.g., "us-east-1")
- `video_bucket`: S3 bucket for storing downloaded videos
- `output_bucket`: S3 bucket for storing transcription outputs
- `prefix`: Optional prefix for S3 keys (e.g., "processed/")
- `endpoint`: Optional custom S3 endpoint URL

### MST Configuration

- `hf_token`: HuggingFace API token for model access
- `ollama_url`: URL of your Ollama server (e.g., "http://host:11434")
- `whisper_model`: Whisper model to use (e.g., "whisper-turbo")
- `llm_model`: LLM model for correction (e.g., "llama3")
- `embedding_model`: Embedding model for topic segmentation
- `min_segment_size`: Minimum segment size in seconds

### Environment Variables

- `SPEAKER_DIARIZATION`: Enable/disable speaker diarization ("true" or "false")

## Output Structure

### S3 Storage Structure

Videos are stored at:
```
s3://{video_bucket}/{prefix}/{channel}/{video_id}/{video_id}.mp4
```

Transcription outputs are stored at:
```
s3://{output_bucket}/{prefix}/{channel}/{video_id}/{video_id}_transcript.md
s3://{output_bucket}/{prefix}/{channel}/{video_id}/{video_id}_transcript.json
```

### Transcription Outputs

**Markdown Format**: Human-readable transcript with:
- Speaker labels (e.g., **Speaker 1:**)
- Timestamps
- Topic hierarchies and segments
- Proper formatting and punctuation

**JSON Format**: Structured data containing:
```json
{
  "video_id": "VlaGzSLsJ_0",
  "title": "Video Title",
  "published_at": "2025-08-20T22:53:57Z",
  "description": "Video description",
  "segments": [
    {
      "start": 0,
      "end": 10,
      "speaker": "Speaker1", 
      "text": "Transcribed text",
      "topic": "Introduction"
    }
  ]
}
```

### Results Tracking

The service generates a `results.json` file tracking processing status:

```json
[
  {
    "url": "https://youtu.be/VIDEO_ID",
    "title": "Video Title",
    "published_at": "2025-08-20T22:53:57Z",
    "description": "Video description",
    "video_id": "VIDEO_ID",
    "channel": "Channel Name",
    "status": "success|failed|skipped",
    "error": "Error details if failed",
    "processed_at": "2025-08-21T12:00:00Z"
  }
]
```

## Error Handling and Reliability

### Retry Logic
- 3 automatic retries for video downloads
- 3 automatic retries for audio extraction
- Graceful handling of network and API failures

### Idempotency
- Automatically skips videos that have already been processed
- Checks S3 for existing outputs before processing
- Uses `results.json` to track processing history

### Error Recovery
- Individual video failures don't stop batch processing
- Detailed error logging for debugging
- Intermediate results saved during processing

## Usage Examples

### Generate Task File from YouTube Channel

Use the included `yt-channel.py` script:

```bash
python yt-channel.py --channel_handle PepperGeek
```

### Run with Custom Speaker Diarization Settings

```bash
# Enable speaker diarization
docker run --gpus all --env SPEAKER_DIARIZATION=true ...

# Disable speaker diarization  
docker run --gpus all --env SPEAKER_DIARIZATION=false ...
```

### Resume Processing After Interruption

The service automatically resumes from where it left off using `results.json`:

```bash
# First run (interrupted)
docker run --gpus all -v $(pwd)/results.json:/app/results.json ...

# Resume processing
docker run --gpus all -v $(pwd)/results.json:/app/results.json ...
```

## Troubleshooting

### Common Issues

**GPU Not Available**:
- Ensure Docker has GPU support: `docker run --gpus all`
- Check NVIDIA drivers and Docker runtime

**Ollama Connection Failed**:
- Verify Ollama server is running and accessible
- Check firewall and network configuration
- Ensure required models are installed in Ollama

**S3 Upload Failures**:
- Verify AWS credentials and permissions
- Check bucket names and region settings
- Ensure buckets exist and are accessible

**MST Import Errors**:
- Verify HuggingFace token is valid
- Check internet connection for model downloads
- Ensure sufficient disk space for model cache

### Logs and Debugging

The service provides detailed logging to stdout. Monitor progress with:

```bash
docker logs -f <container_id>
```

For debugging, check the generated `results.json` file for error details.

## Development

### Project Structure

```
.
├── main.py                 # Main application entry point
├── requirements.txt        # Python dependencies
├── Dockerfile.worker       # Docker build configuration
├── config.example.json     # Configuration template
├── tasks.example.json      # Task file template
├── yt-channel.py          # YouTube channel video fetcher
├── PRD.md                 # Product requirements document
└── README.md              # This file
```

### Building and Testing

```bash
# Build the image
docker build -f Dockerfile.worker -t video-transcription-service .

# Test with sample data
docker run --gpus all \
  -v $(pwd)/config.example.json:/app/config.json \
  -v $(pwd)/tasks.example.json:/app/tasks.json \
  video-transcription-service
```

## License

This project uses the Multi-Step Transcriber library. Please refer to the individual license terms for each dependency.

## Support

For issues and feature requests, please check the logs and configuration first. Common problems are related to:
- Missing or incorrect credentials
- Network connectivity to Ollama/S3
- Insufficient GPU memory or disk space