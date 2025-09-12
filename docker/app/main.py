#!/usr/bin/env python3

import json
import os
import sys
import subprocess
import logging
import tempfile
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, parse_qs

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import yt_dlp
from tqdm import tqdm
from retrying import retry
from multistep_transcriber import MultiStepTranscriber


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def extract_video_id(url: str) -> str:
    """Extract video ID from YouTube URL."""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/v/([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    raise ValueError(f"Could not extract video ID from URL: {url}")


def get_video_metadata(url: str) -> Dict[str, Any]:
    """Get video metadata using yt-dlp."""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return {
                'channel': info.get('uploader', 'unknown'),
                'channel_id': info.get('uploader_id', 'unknown'),
                'duration': info.get('duration', 0),
                'view_count': info.get('view_count', 0)
            }
        except Exception as e:
            logger.warning(f"Could not extract metadata for {url}: {e}")
            return {'channel': 'unknown', 'channel_id': 'unknown', 'duration': 0, 'view_count': 0}


@retry(stop_max_attempt_number=3, wait_fixed=2000)
def download_video(url: str, output_path: str, config: Dict) -> bool:
    """Download video using yt-dlp with retry logic."""
    ydl_opts = {
        'format': config.get('download_options', {}).get('yt_dlp_format', 'best'),
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([url])
            return True
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            raise


@retry(stop_max_attempt_number=3, wait_fixed=2000)
def extract_audio(video_path: str, audio_path: str) -> bool:
    """Extract audio from video using ffmpeg with retry logic."""
    cmd = [
        'ffmpeg', '-i', video_path,
        '-ac', '1',  # mono
        '-ar', '16000',  # 16kHz sample rate
        '-y',  # overwrite output file
        audio_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.debug(f"FFmpeg output: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed: {e.stderr}")
        raise


def upload_to_s3(s3_client, local_path: str, bucket: str, s3_key: str) -> bool:
    """Upload file to S3."""
    try:
        s3_client.upload_file(local_path, bucket, s3_key)
        logger.info(f"Uploaded {local_path} to s3://{bucket}/{s3_key}")
        return True
    except Exception as e:
        logger.error(f"Failed to upload {local_path} to S3: {e}")
        return False


def check_s3_object_exists(s3_client, bucket: str, key: str) -> bool:
    """Check if S3 object exists."""
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        else:
            logger.error(f"Error checking S3 object {bucket}/{key}: {e}")
            return False


def download_json_from_s3(s3_client, bucket: str, key: str, local_path: str) -> bool:
    """Download JSON file from S3."""
    try:
        s3_client.download_file(bucket, key, local_path)
        logger.info(f"Downloaded s3://{bucket}/{key} to {local_path}")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            logger.info(f"File s3://{bucket}/{key} does not exist")
            return False
        else:
            logger.error(f"Failed to download s3://{bucket}/{key}: {e}")
            return False
    except Exception as e:
        logger.error(f"Failed to download s3://{bucket}/{key}: {e}")
        return False


def upload_json_to_s3(s3_client, local_path: str, bucket: str, key: str) -> bool:
    """Upload JSON file to S3."""
    try:
        s3_client.upload_file(local_path, bucket, key)
        logger.info(f"Uploaded {local_path} to s3://{bucket}/{key}")
        return True
    except Exception as e:
        logger.error(f"Failed to upload {local_path} to S3: {e}")
        return False


def setup_s3_client_from_env() -> boto3.client:
    """Setup S3 client with credentials from environment variables."""
    # Use environment variables for AWS credentials (Nomad/Vault integration)
    session = boto3.Session(
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_REGION', 'us-east-1')
    )
    
    s3_kwargs = {}
    if os.getenv('S3_ENDPOINT'):
        s3_kwargs['endpoint_url'] = os.getenv('S3_ENDPOINT')
    
    return session.client('s3', **s3_kwargs)


def setup_s3_client(config: Dict) -> boto3.client:
    """Setup S3 client with credentials from config (legacy)."""
    s3_config = config['s3']
    
    session = boto3.Session(
        aws_access_key_id=s3_config['access_key'],
        aws_secret_access_key=s3_config['secret_key'],
        region_name=s3_config['region']
    )
    
    s3_kwargs = {}
    if 'endpoint' in s3_config and s3_config['endpoint']:
        s3_kwargs['endpoint_url'] = s3_config['endpoint']
    
    return session.client('s3', **s3_kwargs)


def create_config_from_env() -> Dict:
    """Create configuration dictionary from environment variables."""
    return {
        's3': {
            'video_bucket': os.getenv('S3_VIDEO_BUCKET', 'video-bucket'),
            'output_bucket': os.getenv('S3_OUTPUT_BUCKET', 'transcripts-bucket'),
            'tasks_bucket': os.getenv('S3_TASKS_BUCKET', 'tasks-bucket'),
            'prefix': os.getenv('S3_PREFIX', 'processed/'),
            'region': os.getenv('AWS_REGION', 'us-east-1'),
            'endpoint': os.getenv('S3_ENDPOINT', '')
        },
        'mst': {
            'hf_token': os.getenv('HF_TOKEN', ''),
            'ollama_url': os.getenv('OLLAMA_URL', 'http://localhost:11434'),
            'whisper_model': os.getenv('WHISPER_MODEL', 'whisper-turbo'),
            'llm_model': os.getenv('LLM_MODEL', 'llama3'),
            'embedding_model': os.getenv('EMBEDDING_MODEL', 'nomic-embed-text'),
            'min_segment_size': int(os.getenv('MIN_SEGMENT_SIZE', '5'))
        },
        'download_options': {
            'yt_dlp_format': os.getenv('YT_DLP_FORMAT', 'best')
        }
    }


def setup_mst_from_env() -> MultiStepTranscriber:
    """Setup Multi-Step Transcriber from environment variables."""
    # Set HuggingFace token if provided
    hf_token = os.getenv('HF_TOKEN')
    if hf_token:
        os.environ['HF_TOKEN'] = hf_token
    
    # Initialize MST with configuration from environment
    mst = MultiStepTranscriber(
        ollama_url=os.getenv('OLLAMA_URL', 'http://localhost:11434'),
        whisper_model=os.getenv('WHISPER_MODEL', 'whisper-turbo'),
        llm_model=os.getenv('LLM_MODEL', 'llama3'),
        embedding_model=os.getenv('EMBEDDING_MODEL', 'nomic-embed-text'),
    )
    
    return mst


def setup_mst(config: Dict) -> MultiStepTranscriber:
    """Setup Multi-Step Transcriber from config (legacy)."""
    mst_config = config['mst']
    
    # Set HuggingFace token if provided
    if 'hf_token' in mst_config and mst_config['hf_token']:
        os.environ['HF_TOKEN'] = mst_config['hf_token']
    
    # Initialize MST with configuration
    mst = MultiStepTranscriber(
        ollama_url=mst_config['ollama_url'],
        whisper_model=mst_config.get('whisper_model', 'whisper-turbo'),
        llm_model=mst_config.get('llm_model', 'llama3'),
        embedding_model=mst_config.get('embedding_model', 'nomic-embed-text'),
    )
    
    return mst


def transcribe_audio(mst: MultiStepTranscriber, audio_path: str, video_metadata: Dict, 
                    speaker_diarization: bool, config: Dict) -> Dict[str, str]:
    """Transcribe audio using MST and return paths to output files."""
    mst_config = config['mst']
    
    # Prepare transcription parameters
    transcribe_params = {
        'enable_speaker_diarization': speaker_diarization,
    }
    
    # Add any additional MST parameters from config
    if 'min_segment_size' in mst_config:
        transcribe_params['min_segment_size'] = mst_config['min_segment_size']
    
    try:
        # Run MST transcription
        result = mst.transcribe(
            audio_path=audio_path,
            title=video_metadata.get('title', 'Unknown'),
            description=video_metadata.get('description', ''),
            **transcribe_params
        )
        
        # MST should return paths to the generated files
        return {
            'markdown_path': result.get('markdown_path'),
            'json_path': result.get('json_path')
        }
        
    except Exception as e:
        logger.error(f"MST transcription failed: {e}")
        raise


def process_video(task: Dict, config: Dict, s3_client, mst: MultiStepTranscriber, 
                 speaker_diarization: bool, results: List[Dict]) -> Dict:
    """Process a single video task."""
    video_id = extract_video_id(task['url'])
    logger.info(f"Processing video {video_id}: {task['title']}")
    
    result = {
        **task,
        'video_id': video_id,
        'status': 'processing',
        'processed_at': datetime.utcnow().isoformat() + 'Z'
    }
    
    try:
        # Get video metadata
        metadata = get_video_metadata(task['url'])
        channel = metadata['channel']
        result['channel'] = channel
        
        # Check idempotency - see if outputs already exist in S3
        s3_config = config['s3']
        prefix = s3_config.get('prefix', '')
        
        md_key = f"{prefix}{channel}/{video_id}/{video_id}_transcript.md"
        json_key = f"{prefix}{channel}/{video_id}/{video_id}_transcript.json"
        
        if (check_s3_object_exists(s3_client, s3_config['output_bucket'], md_key) and
            check_s3_object_exists(s3_client, s3_config['output_bucket'], json_key)):
            logger.info(f"Outputs already exist for {video_id}, skipping")
            result['status'] = 'skipped'
            return result
        
        # Check if already processed in results
        for prev_result in results:
            if (prev_result.get('video_id') == video_id and 
                prev_result.get('status') == 'success'):
                logger.info(f"Video {video_id} already processed successfully, skipping")
                result['status'] = 'skipped'
                return result
        
        # Create temporary directory for this video
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = os.path.join(temp_dir, f"{video_id}.mp4")
            audio_path = os.path.join(temp_dir, f"{video_id}.wav")
            
            # Download video
            logger.info(f"Downloading video {video_id}")
            download_video(task['url'], video_path, config)
            
            # Upload video to S3
            video_s3_key = f"{prefix}{channel}/{video_id}/{video_id}.mp4"
            if not upload_to_s3(s3_client, video_path, s3_config['video_bucket'], video_s3_key):
                raise Exception("Failed to upload video to S3")
            
            # Extract audio
            logger.info(f"Extracting audio from {video_id}")
            extract_audio(video_path, audio_path)
            
            # Transcribe with MST
            logger.info(f"Transcribing {video_id} with MST")
            transcription_outputs = transcribe_audio(
                mst, audio_path, task, speaker_diarization, config
            )
            
            # Upload transcription outputs to S3
            if transcription_outputs['markdown_path']:
                md_uploaded = upload_to_s3(
                    s3_client, transcription_outputs['markdown_path'], 
                    s3_config['output_bucket'], md_key
                )
            else:
                md_uploaded = False
                
            if transcription_outputs['json_path']:
                json_uploaded = upload_to_s3(
                    s3_client, transcription_outputs['json_path'],
                    s3_config['output_bucket'], json_key
                )
            else:
                json_uploaded = False
            
            if not (md_uploaded and json_uploaded):
                raise Exception("Failed to upload transcription outputs to S3")
            
            logger.info(f"Successfully processed video {video_id}")
            result['status'] = 'success'
            
    except Exception as e:
        logger.error(f"Failed to process video {video_id}: {e}")
        result['status'] = 'failed'
        result['error'] = str(e)
    
    return result


def load_json_file(file_path: str, required: bool = True) -> Optional[Any]:
    """Load JSON file with error handling."""
    if not os.path.exists(file_path):
        if required:
            logger.error(f"Required file not found: {file_path}")
            sys.exit(1)
        else:
            return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {file_path}: {e}")
        if required:
            sys.exit(1)
        return None


def save_results(results: List[Dict], output_path: str = '/app/results.json', 
                 s3_client=None, bucket: str = None, s3_key: str = None):
    """Save results to JSON file and optionally upload to S3."""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"Results saved to {output_path}")
        
        # Upload to S3 if S3 parameters provided
        if s3_client and bucket and s3_key:
            upload_json_to_s3(s3_client, output_path, bucket, s3_key)
            
    except Exception as e:
        logger.error(f"Failed to save results: {e}")


def main():
    """Main entry point."""
    logger.info("Starting YouTube Video Transcription Service")
    
    # Determine configuration mode (env-based or file-based)
    use_s3_mode = os.getenv('USE_S3_CONFIG', 'false').lower() == 'true'
    
    if use_s3_mode:
        logger.info("Using S3-based configuration mode")
        
        # Create configuration from environment variables
        config = create_config_from_env()
        
        # Setup S3 client from environment
        try:
            s3_client = setup_s3_client_from_env()
            logger.info("S3 client initialized from environment")
        except Exception as e:
            logger.error(f"Failed to setup S3 client from environment: {e}")
            sys.exit(1)
        
        # Download tasks.json from S3
        tasks_bucket = os.getenv('S3_TASKS_BUCKET')
        tasks_key = os.getenv('S3_TASKS_KEY', 'tasks.json')
        
        if not tasks_bucket:
            logger.error("S3_TASKS_BUCKET environment variable is required in S3 mode")
            sys.exit(1)
            
        tasks_path = '/tmp/tasks.json'
        if not download_json_from_s3(s3_client, tasks_bucket, tasks_key, tasks_path):
            logger.error(f"Failed to download tasks from s3://{tasks_bucket}/{tasks_key}")
            sys.exit(1)
            
        tasks = load_json_file(tasks_path, required=True)
        logger.info(f"Downloaded and loaded {len(tasks)} video tasks from S3")
        
        # Try to download existing results.json from S3
        results_bucket = os.getenv('S3_RESULTS_BUCKET', tasks_bucket)
        results_key = os.getenv('S3_RESULTS_KEY', 'results.json')
        results_path = '/tmp/results.json'
        
        existing_results = []
        if download_json_from_s3(s3_client, results_bucket, results_key, results_path):
            existing_results = load_json_file(results_path, required=False) or []
            logger.info(f"Downloaded and loaded {len(existing_results)} existing results from S3")
        else:
            logger.info("No existing results found in S3, starting fresh")
        
        # Setup MST from environment
        try:
            mst = setup_mst_from_env()
            logger.info("Multi-Step Transcriber initialized from environment")
        except Exception as e:
            logger.error(f"Failed to setup MST from environment: {e}")
            sys.exit(1)
            
    else:
        logger.info("Using legacy file-based configuration mode")
        
        # Load configuration from files (legacy mode)
        config = load_json_file('/app/config.json', required=True)
        logger.info("Configuration loaded from file")
        
        # Setup S3 client from config
        try:
            s3_client = setup_s3_client(config)
            logger.info("S3 client initialized from config")
        except Exception as e:
            logger.error(f"Failed to setup S3 client from config: {e}")
            sys.exit(1)
        
        # Load tasks from file
        tasks = load_json_file('/app/tasks.json', required=True)
        logger.info(f"Loaded {len(tasks)} video tasks from file")
        
        # Load existing results (optional)
        existing_results = load_json_file('/app/results.json', required=False) or []
        logger.info(f"Loaded {len(existing_results)} existing results from file")
        
        # Setup MST from config
        try:
            mst = setup_mst(config)
            logger.info("Multi-Step Transcriber initialized from config")
        except Exception as e:
            logger.error(f"Failed to setup MST from config: {e}")
            sys.exit(1)
    
    # Validate tasks
    if not isinstance(tasks, list):
        logger.error("Tasks must be an array of video tasks")
        sys.exit(1)
    
    # Get speaker diarization setting from environment
    speaker_diarization = os.getenv('SPEAKER_DIARIZATION', 'true').lower() == 'true'
    logger.info(f"Speaker diarization: {'enabled' if speaker_diarization else 'disabled'}")
    
    # Process videos
    results = []
    any_failures = False
    
    # Setup result saving parameters for S3 mode
    save_params = {}
    if use_s3_mode:
        save_params = {
            's3_client': s3_client,
            'bucket': results_bucket,
            's3_key': results_key
        }
    
    try:
        for task in tqdm(tasks, desc="Processing videos"):
            result = process_video(
                task, config, s3_client, mst, speaker_diarization, existing_results
            )
            results.append(result)
            
            if result['status'] == 'failed':
                any_failures = True
            
            # Save intermediate results
            if use_s3_mode:
                save_results(results, results_path, **save_params)
            else:
                save_results(results)
        
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        if use_s3_mode:
            save_results(results, results_path, **save_params)
        else:
            save_results(results)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if use_s3_mode:
            save_results(results, results_path, **save_params)
        else:
            save_results(results)
        sys.exit(1)
    
    # Final results summary
    success_count = sum(1 for r in results if r['status'] == 'success')
    failed_count = sum(1 for r in results if r['status'] == 'failed')
    skipped_count = sum(1 for r in results if r['status'] == 'skipped')
    
    logger.info(f"Processing complete: {success_count} successful, {failed_count} failed, {skipped_count} skipped")
    
    # Save final results
    if use_s3_mode:
        save_results(results, results_path, **save_params)
    else:
        save_results(results)
    
    # Exit with appropriate code
    sys.exit(1 if any_failures else 0)


if __name__ == '__main__':
    main()