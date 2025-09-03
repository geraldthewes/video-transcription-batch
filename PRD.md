# Product Requirements Document (PRD): YouTube Video Transcription Docker Service

## 1\. Overview

### 1.1 Project Description

This project involves developing a Dockerized Python service that automates the transcription of YouTube videos using the Multi-Step Transcriber (MST) library (available at [https://github.com/geraldthewes/multistep-transcriber](https://github.com/geraldthewes/multistep-transcriber)). The service will process a batch of YouTube videos specified in a JSON task file, download the videos, store them in an S3 bucket, extract audio to WAV format (as required by MST), perform multi-step transcription, and upload the resulting outputs (formatted Markdown and JSON) to a separate S3 bucket.

The MST library implements a high-quality transcription algorithm inspired by open-source workflows (e.g., as described in related Reddit discussions), involving initial transcription with models like Whisper, correction using LLMs, speaker diarization, topic segmentation, and final formatting. This ensures accurate, structured transcripts with features like proper noun correction, punctuation, and hierarchical segmentation.

The service is designed for batch processing and will run as a one-time execution within a Docker container.

### 1.2 Goals

- Automate end-to-end transcription of YouTube videos using MST.  
- Ensure secure handling of S3 storage for videos and outputs.  
- Provide configurable options via a mounted JSON file.  
- Maintain a fully Python-based implementation for simplicity and portability.  
- Support scalability for multiple videos in a single task file.  
- Achieve high transcription quality by leveraging MST's multi-step process.

### 1.3 Target Users

- Developers or AI agents building automated transcription pipelines.  
- Content creators or analysts needing batch processing of YouTube videos.

### 1.4 Assumptions

- An external Ollama server is available for LLM and embedding operations (MST depends on this; the service will not include Ollama internally to avoid complexity and GPU conflicts).  
- Docker container has access to a GPU for efficient model inference (e.g., via `--gpus all` flag).  
- YouTube videos are publicly accessible and downloadable.  
- S3 buckets exist and permissions are set appropriately.  
- The MST library handles audio files up to reasonable lengths; no custom chunking is required unless videos exceed 2 hours (to be handled in error cases).

## 2\. Scope

### 2.1 In Scope

- Docker container setup with Python environment.  
- Reading task JSON (array of video entries) and config JSON via mounted volumes.  
- Downloading YouTube videos using yt-dlp, including metadata extraction for channel.  
- Uploading downloaded videos to a specified S3 bucket using structured paths.  
- Downloading videos from S3 for processing (for persistence and decoupling).  
- Extracting audio to WAV using FFmpeg.  
- Transcribing WAV files using MST.  
- Uploading MST outputs (formatted Markdown and JSON with structured data like segments and speakers) to a separate S3 bucket using structured paths.  
- Generating a results JSON file mapping input tasks to processing states for retry and idempotency.  
- Basic logging, error handling, and retries.  
- Sequential processing of tasks with progress reporting to manage resource usage.

### 2.2 Out of Scope

- Real-time transcription or streaming.  
- Video analysis beyond transcription (e.g., no visual content processing).  
- Automatic creation of S3 buckets or IAM roles.  
- Integration with Ollama setup (assumed external).  
- Web UI or API endpoint; this is a batch CLI-style service.  
- Advanced retry mechanisms beyond specified policies.  
- Support for non-YouTube URLs or non-video content.

## 3\. Functional Requirements

### 3.1 Input Handling

- **Task File**: A JSON file mounted as a volume (e.g., at `/app/tasks.json`). It is an array of objects, each with:  
  - `url`: String (YouTube URL, e.g., "[https://youtu.be/VlaGzSLsJ\_0](https://youtu.be/VlaGzSLsJ_0)").  
  - `title`: String (video title).  
  - `published_at`: String (ISO 8601 timestamp, e.g., "2025-08-20T22:53:57Z").  
  - `description`: String (video description; not used for MST noun extraction).  
- **Config File**: A JSON file mounted as a volume (e.g., at `/app/config.json`). See Section 6 for details.  
- **Results File**: An optional output file mounted as a volume (e.g., at `/app/results.json`). If present on startup, use to skip successfully processed videos; write updated results at end.  
- **Environment Variables**: `SPEAKER_DIARIZATION` (boolean string, e.g., "true" or "false") to enable/disable speaker diarization in MST (if supported by library; otherwise, log warning).  
- The service starts by loading these files on container startup.

### 3.2 Processing Workflow

Use tqdm to display progress bar for the loop over tasks.

For each video entry in the task file (processed sequentially):

1. **Check Idempotency**:  
     
   - Extract video ID from URL (e.g., "VlaGzSLsJ\_0").  
   - Use yt-dlp to fetch metadata (e.g., `yt-dlp --dump-json`) to get `channel` (fallback to "unknown" if unavailable).  
   - Check if output Markdown and JSON exist in S3 (use boto3 head\_object on expected paths).  
   - If both exist, skip and mark as "success" in results.  
   - Also check results.json if loaded for prior state.

   

2. **Download Video**:  
     
   - Use yt-dlp to download the full video in MP4 format (best quality available).  
   - Retry up to 3 times on failure (use retrying library or similar).  
   - Temporary local path: `/tmp/{video_id}.mp4`.

   

3. **Store Video in S3**:  
     
   - Upload the MP4 to the video S3 bucket specified in config.  
   - Path: `s3://{video_bucket}/{prefix}/{channel}/{video_id}/{video_id}.mp4`.  
   - Use boto3 with credentials from config.

   

4. **Extract Audio**:  
     
   - Use FFmpeg to extract audio to WAV format (mono, 16kHz sample rate for MST compatibility) from the above downloaded video.  
   - Use Python's subprocess module to invoke the system ffmpeg command.  
   - Command: `ffmpeg -i /tmp/{video_id}.mp4 -ac 1 -ar 16000 /tmp/{video_id}.wav`.  
   - Handle errors if extraction fails (e.g., invalid video); retry up to 3 times.

   

5. **Transcribe with MST**:  
     
   - Invoke MST's transcription function on the WAV file.  
   - Configure speaker diarization based on `SPEAKER_DIARIZATION` env var (pass as param if MST supports; e.g., skip diarization step if false).  
   - Do not use video description for noun extraction.  
   - MST Process (based on library implementation):.  
   - Outputs from MST:  
     - Formatted Markdown file (e.g., `{video_id}_transcript.md`) with speaker labels, timestamps, and segments (if diarization enabled).  
     - JSON final file (e.g., `{video_id}_transcript.json`) containing structured data: list of segments, speakers, timestamps, text, and metadata (title, published\_at, description).

   

6. **Store Outputs in S3**:  
     
   - Upload MST outputs to the output S3 bucket.  
   - Path: `s3://{output_bucket}/{prefix}/{channel}/{video_id}/{filename}` (e.g., for md, json).  
   - Clean up local temporary files after upload.

   

7. **Update Results**:  
     
   - For each video, record state in results dict: e.g., {"video\_id": "...", "status": "success" | "failed", "error": "details if failed", "processed\_at": timestamp}.  
   - Write full results.json at end, mapping all inputs with states.

### 3.3 Output Formats

- **Formatted Markdown**: Readable MD with sections, speaker labels (e.g., **Speaker 1:**), timestamps, and topic hierarchies (if diarization enabled).  
- **JSON Final**: Structured JSON, e.g.:  
    
  {  
    
    "video\_id": "VlaGzSLsJ\_0",  
    
    "title": "Stop buying pickles...",  
    
    "published\_at": "2025-08-20T22:53:57Z",  
    
    "description": "...",  
    
    "segments": \[  
    
      {"start": 0, "end": 10, "speaker": "Speaker1", "text": "...", "topic": "Introduction"},  
    
      ...  
    
    \]  
    
  }  
    
- All files named consistently based on video\_id (e.g., {video\_id}\_transcript.md, {video\_id}\_transcript.json).  
- **Results JSON**: Array of objects mirroring tasks with added fields:  
    
  \[  
    
    {  
    
      "url": "...",  
    
      "title": "...",  
    
      "published\_at": "...",  
    
      "description": "...",  
    
      "video\_id": "...",  
    
      "channel": "...",  
    
      "status": "success" | "failed" | "skipped" | "downloaded",  
    
      "error": "..." (if failed),  
    
      "processed\_at": "2025-08-21T12:00:00Z"  
    
    },  
    
    ...  
    
  \]

### 3.4 Error Handling and Logging

- Log all steps to stdout/stderr (use Python logging module).  
- On failure (e.g., download error, transcription failure): Log details, mark as "failed" in results, skip to next task, and continue.  
- Retries: 3 attempts for download and audio extraction steps.  
- Use results.json for reprocessing: On re-run with same tasks, skip "success" or if outputs exist.  
- Exit codes: 0 on all success, 1 if any failure.

## 4\. Non-Functional Requirements

### 4.1 Performance

- Process videos sequentially to avoid OOM on GPU.  
- Use tqdm for progress output during processing.

### 4.2 Security

- Store S3 credentials only in config JSON (not hardcoded).  
- Use environment variables for sensitive keys if needed, but prefer config file.  
- No exposure of APIs; internal service only.

### 4.3 Reliability

- Idempotent: If re-run, check if outputs exist in S3 and skip if present (use S3 head\_object to check), update results.json accordingly.  
- Clean up temporary files on exit.  
- Retry policies: 3 retries for critical steps (download, extraction).

### 4.4 Scalability

- For larger batches, users can run multiple containers.  
- No built-in parallelism.

## 5\. Technical Specifications

### 5.1 Architecture

- **Language**: Python 3.12.  
- **Docker**: Base image ubuntu:24.04  
- **Entry Point**: Python script `/app/main.py` run on container start.  
- **Data Flow**:  
  - Mount volumes: `-v /host/tasks.json:/app/tasks.json -v /host/config.json:/app/config.json -v /host/results.json:/app/results.json`.  
  - Run: `docker run --gpus all --env SPEAKER_DIARIZATION=true -v ... transcription-service`.

### 5.2 Dependencies

- **Python Packages** (install via pip in Dockerfile):  
  - `yt-dlp`: For YouTube downloading and metadata.  
  - `boto3`: For S3 interactions.  
  - `torch` (with CUDA: `pip install torch --index-url https://download.pytorch.org/whl/cu126`).  
  - `git+https://github.com/geraldthewes/topic-treeseg.git`: Required by MST.  
  - `git+https://github.com/geraldthewes/multistep-transcriber.git`: The MST library itself.  
  - `whisperx`: For initial transcription (if not bundled in MST).  
  - `pyannote.audio`: For speaker diarization.  
  - `ollama`: Python client for Ollama API.  
  - `huggingface_hub`: For model downloads.  
  - `tqdm`: For progress bars.  
  - `retrying`: For retry decorators.  
- **System Dependencies** (install via apt in Dockerfile):  
  - `ffmpeg`: For audio extraction.  
  - `git`: For cloning repos.

5.3 Dockerfile Suggestion

This docker file was used for a service and has the right library dependencies. Only change the part relevant to this project

\# Use Ubuntu 24.04 LTS as the base image  
FROM ubuntu:24.04

\# Set environment variables to avoid interactive prompts  
ENV DEBIAN\_FRONTEND=noninteractive

\# Install basic dependencies and tools  
RUN apt-get update && apt-get install \-y \\  
    git \\  
    gcc \\  
    g++ \\  
    build-essential \\  
    liblzma-dev \\  
    zlib1g-dev \\  
    libbz2-dev \\  
    libffi-dev \\  
    python3.12 \\  
    python3.12-dev \\  
    python3-pip \\  
    curl \\  
    && apt-get clean \\  
    && rm \-rf /var/lib/apt/lists/\*

\# Disable the very annoying PEP 668 (in a container)  
RUN rm /usr/lib/python3.12/EXTERNALLY-MANAGED

\# Install NVIDIA CUDA 12.8 and related libraries  
RUN curl \-fsSL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86\_64/cuda-keyring\_1.1-1\_all.deb \-o cuda-keyring.deb \\  
    && dpkg \-i cuda-keyring.deb \\  
    && rm cuda-keyring.deb \\  
    && apt-get update \\  
    && apt-get install \-y \\  
        cuda-toolkit-12-8 \\  
    && apt-get clean \\  
    && rm \-rf /var/lib/apt/lists/\*

\# Set environment variables for CUDA  
ENV PATH=/usr/local/cuda-12.8/bin:${PATH}  
ENV LD\_LIBRARY\_PATH=/usr/local/cuda-12.8/lib64:${LD\_LIBRARY\_PATH}

\# Install cuDNN via pip to provide the required libraries  
RUN pip3 install \--no-cache-dir \--break-system-packages nvidia-cudnn-cu12==9.1.0.70  
ENV LD\_LIBRARY\_PATH=${LD\_LIBRARY\_PATH}:/usr/local/lib/python3.12/dist-packages/nvidia/cudnn/lib/

\# Set the working directory in the container  
WORKDIR /app

\# Copy requirements file first for better Docker layer caching  
COPY requirements.txt /app/

\# Install Python dependencies  
RUN pip3 install \--no-cache-dir \--break-system-packages \-r requirements.txt

\# Load necessary models  
RUN python3 \-m spacy download en\_core\_web\_sm

\# Copy the transcriber\_service package into the container  
COPY ./transcriber\_service /app/transcriber\_service

\# Command to run the Celery worker  
CMD \["celery", "-A", "transcriber\_service.tasks.transcription.celery\_app", "worker", "-l", "INFO", "-P", "solo"\]

### 5.4 Main Script Structure (`main.py`)

- Import dependencies (including tqdm, retrying).  
- Load config, tasks, and optional results JSON.  
- Use tqdm for loop over tasks.  
- For each: Check skip, download with retry, upload, download, extract with retry, transcribe (pass diarization flag if supported), upload, update results dict.  
- Write results.json at end.  
- Handle exceptions per step, log, and set status.

## 6\. Configuration

All in `/app/config.json`:

{

  "s3": {

    "access\_key": "AKIA...",

    "secret\_key": "abc...",

    "region": "us-east-1",

    "video\_bucket": "yt-videos-bucket",

    "output\_bucket": "transcripts-bucket",

    "prefix": "processed/",

    "endpoint"

  },

  "mst": {

    "hf\_token": "hf\_...",

    "ollama\_url": "http://ollama-host:11434",

    "whisper\_model": "whisper-turbo",

    "llm\_model": "llama3",

    "embedding\_model": "nomic-embed-text",

    "min\_segment\_size": 5  // Example MST params

  },

  "download\_options": {

    "yt\_dlp\_format": "best"  // Custom yt-dlp flags

  }

}

- Load with `json.load` and pass to relevant components.  
- HF\_TOKEN can also be set as env var if preferred.

## 7\. Testing Requirements

- Unit tests for each step (e.g., mock S3 with moto, mock MST, mock yt-dlp).  
- Integration test: Run Docker with sample task file, verify S3 uploads, results.json, and progress output.  
- Use pytest.

## 8\. Documentation

- Include README.md in repo with setup instructions, example config/task/results files, Docker run commands, and environment variable usage.

