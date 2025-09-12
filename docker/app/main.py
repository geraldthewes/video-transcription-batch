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


def setup_s3_client() -> boto3.client:
    """Setup S3 client with credentials from environment variables."""
    session = boto3.Session(
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_REGION', 'us-east-1')
    )
    
    s3_kwargs = {}
    if os.getenv('S3_ENDPOINT'):
        s3_kwargs['endpoint_url'] = os.getenv('S3_ENDPOINT')
    
    return session.client('s3', **s3_kwargs)




def create_config_from_env() -> Dict:
    """Create configuration dictionary from environment variables."""
    return {
        's3': {
            'transcriber_bucket': os.getenv('S3_TRANSCRIBER_BUCKET'),
            'transcriber_prefix': os.getenv('S3_TRANSCRIBER_PREFIX', ''),
            'job_id': os.getenv('S3_JOB_ID'),
            'video_bucket': os.getenv('S3_VIDEO_BUCKET', 'video-bucket'),
            'output_bucket': os.getenv('S3_OUTPUT_BUCKET', 'transcripts-bucket'),
            'region': os.getenv('AWS_REGION', 'us-east-1'),
            'endpoint': os.getenv('S3_ENDPOINT', '')
        },
        'mst': {
            'hf_token': os.getenv('HF_TOKEN', ''),
            'ollama_url': os.getenv('OLLAMA_URL', 'http://localhost:11434'),
            # Default values - will be overridden by config.json if present
            'whisper_model': os.getenv('WHISPER_MODEL', 'whisper-turbo'),
            'llm_model': os.getenv('LLM_MODEL', 'llama3'),
            'embedding_model': os.getenv('EMBEDDING_MODEL', 'nomic-embed-text'),
            'min_segment_size': int(os.getenv('MIN_SEGMENT_SIZE', '5'))
        },
        'download_options': {
            'yt_dlp_format': os.getenv('YT_DLP_FORMAT', 'best')
        }
    }


def setup_mst(config: Dict) -> MultiStepTranscriber:
    """Setup Multi-Step Transcriber from configuration."""
    mst_config = config['mst']
    
    # Set HuggingFace token if provided
    hf_token = mst_config.get('hf_token')
    if hf_token:
        os.environ['HF_TOKEN'] = hf_token
    
    # Initialize MST with configuration
    mst = MultiStepTranscriber(
        ollama_url=mst_config['ollama_url'],
        whisper_model=mst_config['whisper_model'],
        llm_model=mst_config['llm_model'],
        embedding_model=mst_config['embedding_model'],
    )
    
    return mst


def transcribe_audio(mst: MultiStepTranscriber, audio_path: str, video_metadata: Dict, 
                    speaker_diarization: bool, config: Dict, transcription_config: Dict) -> Dict[str, str]:
    """Transcribe audio using MST and return paths to output files."""
    mst_config = config['mst']
    
    # Prepare transcription parameters
    transcribe_params = {
        'enable_speaker_diarization': speaker_diarization,
    }
    
    # Add parameters from transcription_config (overrides defaults)
    if 'min_segment_size' in transcription_config:
        transcribe_params['min_segment_size'] = transcription_config['min_segment_size']
    elif 'min_segment_size' in mst_config:
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


def process_video(task: Dict, config: Dict, transcription_config: Dict, s3_client, mst: MultiStepTranscriber, 
                 results: List[Dict]) -> Dict:
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
        transcriber_prefix = s3_config.get('transcriber_prefix', '')
        job_id = s3_config['job_id']
        
        # Ensure prefix ends with / if not empty
        if transcriber_prefix and not transcriber_prefix.endswith('/'):
            transcriber_prefix += '/'
            
        md_key = f"{transcriber_prefix}{job_id}/outputs/{channel}/{video_id}/{video_id}_transcript.md"
        json_key = f"{transcriber_prefix}{job_id}/outputs/{channel}/{video_id}/{video_id}_transcript.json"
        
        if (check_s3_object_exists(s3_client, s3_config['transcriber_bucket'], md_key) and
            check_s3_object_exists(s3_client, s3_config['transcriber_bucket'], json_key)):
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
            
            # Upload video to S3 inputs directory
            video_s3_key = f"{transcriber_prefix}{job_id}/inputs/{channel}/{video_id}/{video_id}.mp4"
            if not upload_to_s3(s3_client, video_path, s3_config['transcriber_bucket'], video_s3_key):
                raise Exception("Failed to upload video to S3")
            
            # Extract audio
            logger.info(f"Extracting audio from {video_id}")
            extract_audio(video_path, audio_path)
            
            # Transcribe with MST
            logger.info(f"Transcribing {video_id} with MST")
            speaker_diarization = transcription_config.get('speaker_diarization', True)
            transcription_outputs = transcribe_audio(
                mst, audio_path, task, speaker_diarization, config, transcription_config
            )
            
            # Upload transcription outputs to S3
            if transcription_outputs['markdown_path']:
                md_uploaded = upload_to_s3(
                    s3_client, transcription_outputs['markdown_path'], 
                    s3_config['transcriber_bucket'], md_key
                )
            else:
                md_uploaded = False
                
            if transcription_outputs['json_path']:
                json_uploaded = upload_to_s3(
                    s3_client, transcription_outputs['json_path'],
                    s3_config['transcriber_bucket'], json_key
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


def load_and_merge_transcription_config(config: Dict, transcription_config: Dict) -> Dict:
    """Load transcription config and merge with MST defaults."""
    mst_config = config['mst'].copy()
    
    # Override with transcription-specific config
    if 'whisper_model' in transcription_config:
        mst_config['whisper_model'] = transcription_config['whisper_model']
    if 'llm_model' in transcription_config:
        mst_config['llm_model'] = transcription_config['llm_model']  
    if 'embedding_model' in transcription_config:
        mst_config['embedding_model'] = transcription_config['embedding_model']
    if 'min_segment_size' in transcription_config:
        mst_config['min_segment_size'] = transcription_config['min_segment_size']
    
    # Override download options
    download_options = config['download_options'].copy()
    if 'yt_dlp_format' in transcription_config:
        download_options['yt_dlp_format'] = transcription_config['yt_dlp_format']
    
    # Create updated config
    updated_config = config.copy()
    updated_config['mst'] = mst_config
    updated_config['download_options'] = download_options
    
    return updated_config


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
    logger.info("Starting YouTube Video Transcription Service v4.0.0")
    
    # Create configuration from environment variables
    config = create_config_from_env()
    s3_config = config['s3']
    
    # Validate required environment variables
    if not s3_config['transcriber_bucket']:
        logger.error("S3_TRANSCRIBER_BUCKET environment variable is required")
        sys.exit(1)
    if not s3_config['job_id']:
        logger.error("S3_JOB_ID environment variable is required")
        sys.exit(1)
    
    # Setup S3 client from environment
    try:
        s3_client = setup_s3_client()
        logger.info("S3 client initialized")
    except Exception as e:
        logger.error(f"Failed to setup S3 client: {e}")
        sys.exit(1)
    
    # Construct S3 paths using new structure
    transcriber_prefix = s3_config['transcriber_prefix']
    if transcriber_prefix and not transcriber_prefix.endswith('/'):
        transcriber_prefix += '/'
    job_id = s3_config['job_id']
    
    tasks_key = f"{transcriber_prefix}{job_id}/tasks.json"
    config_key = f"{transcriber_prefix}{job_id}/config.json"
    results_key = f"{transcriber_prefix}{job_id}/results.json"
    
    # Download tasks.json from S3
    tasks_path = '/tmp/tasks.json'
    if not download_json_from_s3(s3_client, s3_config['transcriber_bucket'], tasks_key, tasks_path):
        logger.error(f"Failed to download tasks from s3://{s3_config['transcriber_bucket']}/{tasks_key}")
        sys.exit(1)
        
    tasks = load_json_file(tasks_path, required=True)
    logger.info(f"Downloaded and loaded {len(tasks)} video tasks from S3")
    
    # Try to download transcription config.json from S3
    transcription_config = {}
    config_path = '/tmp/config.json'
    if download_json_from_s3(s3_client, s3_config['transcriber_bucket'], config_key, config_path):
        transcription_config = load_json_file(config_path, required=False) or {}
        logger.info(f"Downloaded transcription config with {len(transcription_config)} parameters")
    else:
        logger.info("No transcription config found, using defaults")
    
    # Merge transcription config with base config
    if transcription_config:
        config = load_and_merge_transcription_config(config, transcription_config)
        logger.info("Applied transcription-specific configuration")
    
    # Try to download existing results.json from S3
    results_path = '/tmp/results.json'
    existing_results = []
    if download_json_from_s3(s3_client, s3_config['transcriber_bucket'], results_key, results_path):
        existing_results = load_json_file(results_path, required=False) or []
        logger.info(f"Downloaded and loaded {len(existing_results)} existing results from S3")
    else:
        logger.info("No existing results found in S3, starting fresh")
    
    # Setup MST from environment
    try:
        mst = setup_mst(config)
        logger.info("Multi-Step Transcriber initialized")
    except Exception as e:
        logger.error(f"Failed to setup MST: {e}")
        sys.exit(1)
    
    # Validate tasks
    if not isinstance(tasks, list):
        logger.error("Tasks must be an array of video tasks")
        sys.exit(1)
    
    # Process videos
    results = []
    any_failures = False
    
    # Setup result saving parameters
    save_params = {
        's3_client': s3_client,
        'bucket': s3_config['transcriber_bucket'],
        's3_key': results_key
    }
    
    try:
        for task in tqdm(tasks, desc="Processing videos"):
            result = process_video(
                task, config, transcription_config, s3_client, mst, existing_results
            )
            results.append(result)
            
            if result['status'] == 'failed':
                any_failures = True
            
            # Save intermediate results
            save_results(results, results_path, **save_params)
        
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        save_results(results, results_path, **save_params)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        save_results(results, results_path, **save_params)
        sys.exit(1)
    
    # Final results summary
    success_count = sum(1 for r in results if r['status'] == 'success')
    failed_count = sum(1 for r in results if r['status'] == 'failed')
    skipped_count = sum(1 for r in results if r['status'] == 'skipped')
    
    logger.info(f"Processing complete: {success_count} successful, {failed_count} failed, {skipped_count} skipped")
    
    # Save final results
    save_results(results, results_path, **save_params)
    
    # Exit with appropriate code
    sys.exit(1 if any_failures else 0)


if __name__ == '__main__':
    main()