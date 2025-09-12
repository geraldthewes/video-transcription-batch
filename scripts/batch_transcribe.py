#!/usr/bin/env python3
"""
Command-line utility for managing S3-based batch transcription jobs.
"""

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Optional

# Add the parent directory to Python path to import transcription_client
sys.path.insert(0, str(Path(__file__).parent.parent))

from transcription_client.s3_batch import S3BatchManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_env_file(env_file: str = '.env'):
    """
    Load environment variables from .env file.
    
    Args:
        env_file: Path to the .env file
    """
    env_path = Path(env_file)
    if not env_path.exists():
        logger.warning(f"Environment file not found: {env_file}")
        return
    
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and not os.getenv(key):  # Don't override existing env vars
                    os.environ[key] = value
    
    logger.info(f"Loaded environment variables from {env_file}")


def create_manager_from_env(aws_profile: Optional[str] = None) -> S3BatchManager:
    """Create S3BatchManager using environment variables."""
    return S3BatchManager(
        aws_region=os.getenv('AWS_REGION', 'us-east-1'),
        aws_profile=aws_profile,
        s3_endpoint=os.getenv('S3_ENDPOINT_URL'),
        transcriber_bucket=os.getenv('S3_TRANSCRIBER_BUCKET'),
        transcriber_prefix=os.getenv('S3_TRANSCRIBER_PREFIX', ''),
    )


def upload_tasks(args):
    """Upload tasks from a JSON file to S3."""
    logger.info(f"Using AWS profile: {args.profile}")
    manager = create_manager_from_env(aws_profile=args.profile)
    
    # Load tasks from file
    tasks = manager.load_tasks_file(args.tasks_file)
    
    # Create transcription configuration
    transcription_config = {}
    if hasattr(args, 'whisper_model') and args.whisper_model:
        transcription_config['whisper_model'] = args.whisper_model
    if hasattr(args, 'llm_model') and args.llm_model:
        transcription_config['llm_model'] = args.llm_model
    if hasattr(args, 'embedding_model') and args.embedding_model:
        transcription_config['embedding_model'] = args.embedding_model
    if hasattr(args, 'min_segment_size') and args.min_segment_size:
        transcription_config['min_segment_size'] = args.min_segment_size
    if hasattr(args, 'speaker_diarization') and args.speaker_diarization is not None:
        transcription_config['speaker_diarization'] = args.speaker_diarization
    if hasattr(args, 'yt_dlp_format') and args.yt_dlp_format:
        transcription_config['yt_dlp_format'] = args.yt_dlp_format
    
    # Upload to S3
    job_id = manager.upload_tasks(
        tasks, 
        job_id=args.job_id,
        transcription_config=transcription_config if transcription_config else None
    )
    
    print(f"✅ Uploaded {len(tasks)} tasks to S3")
    print(f"📋 Job ID: {job_id}")
    print(f"🗂️  Tasks: s3://{manager.transcriber_bucket}/{manager.transcriber_prefix}{job_id}/tasks.json")
    print(f"📊 Results: s3://{manager.transcriber_bucket}/{manager.transcriber_prefix}{job_id}/results.json")
    print(f"📁 Inputs: s3://{manager.transcriber_bucket}/{manager.transcriber_prefix}{job_id}/inputs/")
    print(f"📁 Outputs: s3://{manager.transcriber_bucket}/{manager.transcriber_prefix}{job_id}/outputs/")
    
    # Generate environment variables for Nomad
    if args.generate_env:
        env_vars = manager.create_nomad_env_vars(
            job_id=job_id,
            ollama_url=args.ollama_url or os.getenv('OLLAMA_URL', 'http://ollama:11434'),
            hf_token=args.hf_token or os.getenv('HF_TOKEN')
        )
        
        print("\n🔧 Nomad Environment Variables:")
        for key, value in env_vars.items():
            print(f'      {key} = "{value}"')


def status(args):
    """Check the status of a transcription job."""
    manager = create_manager_from_env(aws_profile=args.profile)
    
    status_info = manager.get_job_status(args.job_id)
    
    print(f"📋 Job ID: {status_info['job_id']}")
    print(f"📊 Status: {status_info['status'].upper()}")
    print(f"📈 Progress: {status_info['progress']:.1%}")
    print(f"✅ Completed: {status_info['completed_tasks']}/{status_info['total_tasks']}")
    print(f"❌ Failed: {status_info['failed_tasks']}")
    print(f"⏭️  Skipped: {status_info['skipped_tasks']}")
    
    if status_info.get('processing_tasks', 0) > 0:
        print(f"🔄 Processing: {status_info['processing_tasks']}")


def list_jobs(args):
    """List all transcription jobs."""
    manager = create_manager_from_env(aws_profile=args.profile)
    
    job_ids = manager.list_jobs()
    
    if not job_ids:
        print("No jobs found.")
        return
    
    print(f"Found {len(job_ids)} jobs:\n")
    
    for job_id in job_ids:
        try:
            status_info = manager.get_job_status(job_id)
            print(f"📋 {job_id}")
            print(f"   Status: {status_info['status'].upper()}")
            print(f"   Progress: {status_info['progress']:.1%} ({status_info['completed_tasks']}/{status_info['total_tasks']})")
            print()
        except Exception as e:
            print(f"📋 {job_id}")
            print(f"   Error: {e}")
            print()


def download_results(args):
    """Download results from S3 to a local file."""
    manager = create_manager_from_env(aws_profile=args.profile)
    
    results = manager.download_results(args.job_id)
    
    if not results:
        print(f"❌ No results found for job {args.job_id}")
        return
    
    # Save to file
    output_path = args.output or f"results-{args.job_id}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Downloaded {len(results)} results to {output_path}")


def view_config(args):
    """View transcription configuration for a job."""
    manager = create_manager_from_env(aws_profile=args.profile)
    
    config = manager.download_config(args.job_id)
    
    if not config:
        print(f"❌ No transcription config found for job {args.job_id}")
        return
    
    print(f"📋 Job ID: {args.job_id}")
    print("🔧 Transcription Configuration:")
    for key, value in config.items():
        print(f"   {key}: {value}")


def create_tasks(args):
    """Create a tasks.json file with example content."""
    example_tasks = [
        {
            "url": "https://youtu.be/VlaGzSLsJ_0",
            "title": "Stop buying pickles and make them at home",
            "published_at": "2025-08-20T22:53:57Z",
            "description": "Learn how to make delicious pickles at home with this simple recipe."
        },
        {
            "url": "https://youtu.be/dQw4w9WgXcQ", 
            "title": "Another Example Video",
            "published_at": "2025-08-19T15:30:00Z",
            "description": "This is another example video entry."
        }
    ]
    
    # Generate UUID-based filename if no output specified
    if args.output:
        output_path = args.output
    else:
        task_uuid = str(uuid.uuid4())
        output_path = f"{task_uuid}.json"
        print(f"📋 Generated task UUID: {task_uuid}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(example_tasks, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Created tasks file: {output_path}")
    print("📝 Edit this file with your actual video URLs and upload with:")
    print(f"   python -m scripts.batch_transcribe upload {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Manage S3-based batch transcription jobs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Setup: Copy and customize environment file
  cp env-template .env && nano .env
  
  # Create tasks file
  python -m scripts.batch_transcribe create-task --output my-videos.json

  # Upload tasks with transcription parameters (with AWS profile)
  python -m scripts.batch_transcribe upload my-videos.json \\
    --profile my-aws-profile --whisper-model whisper-turbo --speaker-diarization \\
    --min-segment-size 5 --generate-env \\
    --ollama-url http://ollama.service.consul:11434

  # Check job status
  python -m scripts.batch_transcribe status abc-123-def --profile my-aws-profile
  
  # View transcription configuration
  python -m scripts.batch_transcribe config abc-123-def --profile my-aws-profile

  # List all jobs
  python -m scripts.batch_transcribe list --profile my-aws-profile

  # Download results
  python -m scripts.batch_transcribe download abc-123-def --output results.json --profile my-aws-profile
        """
    )
    
    # Configuration
    parser.add_argument('--env-file', default='.env', help='Environment file to load (default: .env)')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Upload command
    upload_parser = subparsers.add_parser('upload', help='Upload tasks to S3')
    upload_parser.add_argument('tasks_file', help='Path to tasks.json file')
    upload_parser.add_argument('--job-id', help='Custom job ID (generates UUID if not provided)')
    upload_parser.add_argument('--profile', help='AWS profile name for credentials (uses ~/.aws/credentials)')
    upload_parser.add_argument('--generate-env', action='store_true', 
                              help='Generate Nomad environment variables')
    upload_parser.add_argument('--ollama-url', help='Ollama service URL (for --generate-env)')
    upload_parser.add_argument('--hf-token', help='HuggingFace token')
    
    # Transcription parameters
    upload_parser.add_argument('--whisper-model', help='Whisper model to use (e.g., whisper-turbo)')
    upload_parser.add_argument('--llm-model', help='LLM model to use (e.g., llama3)')  
    upload_parser.add_argument('--embedding-model', help='Embedding model to use (e.g., nomic-embed-text)')
    upload_parser.add_argument('--min-segment-size', type=int, help='Minimum segment size in seconds')
    upload_parser.add_argument('--speaker-diarization', action='store_true', help='Enable speaker diarization')
    upload_parser.add_argument('--no-speaker-diarization', dest='speaker_diarization', action='store_false', help='Disable speaker diarization')
    upload_parser.add_argument('--yt-dlp-format', help='yt-dlp format string (e.g., best)')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Check job status')
    status_parser.add_argument('job_id', help='Job ID to check')
    status_parser.add_argument('--profile', help='AWS profile name for credentials (uses ~/.aws/credentials)')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List all jobs')
    list_parser.add_argument('--profile', help='AWS profile name for credentials (uses ~/.aws/credentials)')
    
    # Download command
    download_parser = subparsers.add_parser('download', help='Download results')
    download_parser.add_argument('job_id', help='Job ID to download results for')
    download_parser.add_argument('--output', help='Output file path (default: results-{job_id}.json)')
    download_parser.add_argument('--profile', help='AWS profile name for credentials (uses ~/.aws/credentials)')
    
    # Config command
    config_parser = subparsers.add_parser('config', help='View transcription configuration for a job')
    config_parser.add_argument('job_id', help='Job ID to view config for')
    config_parser.add_argument('--profile', help='AWS profile name for credentials (uses ~/.aws/credentials)')
    
    # Create task command
    task_parser = subparsers.add_parser('create-task', help='Create tasks.json file with example content')
    task_parser.add_argument('--output', help='Output file path (default: <uuid>.json)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Load environment variables
    load_env_file(args.env_file)
    
    try:
        if args.command == 'upload':
            upload_tasks(args)
        elif args.command == 'status':
            status(args)
        elif args.command == 'list':
            list_jobs(args)
        elif args.command == 'download':
            download_results(args)
        elif args.command == 'config':
            view_config(args)
        elif args.command == 'create-task':
            create_tasks(args)
            
    except Exception as e:
        logger.error(f"Command failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()