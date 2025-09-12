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

# Add the parent directory to Python path to import transcription_client
sys.path.insert(0, str(Path(__file__).parent.parent))

from transcription_client.s3_batch import S3BatchManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def upload_tasks(args):
    """Upload tasks from a JSON file to S3."""
    manager = S3BatchManager(
        aws_region=args.region,
        s3_endpoint=args.s3_endpoint,
        tasks_bucket=args.tasks_bucket,
        results_bucket=args.results_bucket
    )
    
    # Load tasks from file
    tasks = manager.load_tasks_file(args.tasks_file)
    
    # Upload to S3
    job_id = manager.upload_tasks(tasks, job_id=args.job_id)
    
    print(f"✅ Uploaded {len(tasks)} tasks to S3")
    print(f"📋 Job ID: {job_id}")
    print(f"🗂️  Tasks: s3://{manager.tasks_bucket}/jobs/{job_id}/tasks.json")
    print(f"📊 Results: s3://{manager.results_bucket}/jobs/{job_id}/results.json")
    
    # Generate environment variables for Nomad
    if args.generate_env:
        env_vars = manager.create_nomad_env_vars(
            job_id=job_id,
            video_bucket=args.video_bucket or 'video-bucket',
            output_bucket=args.output_bucket or 'transcripts-bucket',
            ollama_url=args.ollama_url or 'http://ollama:11434',
            hf_token=args.hf_token
        )
        
        print("\n🔧 Nomad Environment Variables:")
        for key, value in env_vars.items():
            print(f'      {key} = "{value}"')


def status(args):
    """Check the status of a transcription job."""
    manager = S3BatchManager(
        aws_region=args.region,
        s3_endpoint=args.s3_endpoint,
        tasks_bucket=args.tasks_bucket,
        results_bucket=args.results_bucket
    )
    
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
    manager = S3BatchManager(
        aws_region=args.region,
        s3_endpoint=args.s3_endpoint,
        tasks_bucket=args.tasks_bucket,
        results_bucket=args.results_bucket
    )
    
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
    manager = S3BatchManager(
        aws_region=args.region,
        s3_endpoint=args.s3_endpoint,
        tasks_bucket=args.tasks_bucket,
        results_bucket=args.results_bucket
    )
    
    results = manager.download_results(args.job_id)
    
    if not results:
        print(f"❌ No results found for job {args.job_id}")
        return
    
    # Save to file
    output_path = args.output or f"results-{args.job_id}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Downloaded {len(results)} results to {output_path}")


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
  # Create tasks file
  python -m scripts.batch_transcribe create-task --output my-videos.json

  # Upload tasks and get Nomad environment variables  
  python -m scripts.batch_transcribe upload my-videos.json --generate-env \\
    --video-bucket my-videos --output-bucket my-transcripts \\
    --ollama-url http://ollama.example.com:11434

  # Check job status
  python -m scripts.batch_transcribe status abc-123-def

  # List all jobs
  python -m scripts.batch_transcribe list

  # Download results
  python -m scripts.batch_transcribe download abc-123-def --output results.json
        """
    )
    
    # Common arguments
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--s3-endpoint', help='Custom S3 endpoint URL')
    parser.add_argument('--tasks-bucket', help='S3 bucket for tasks (or set S3_TASKS_BUCKET env var)')
    parser.add_argument('--results-bucket', help='S3 bucket for results (defaults to tasks bucket)')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Upload command
    upload_parser = subparsers.add_parser('upload', help='Upload tasks to S3')
    upload_parser.add_argument('tasks_file', help='Path to tasks.json file')
    upload_parser.add_argument('--job-id', help='Custom job ID (generates UUID if not provided)')
    upload_parser.add_argument('--generate-env', action='store_true', 
                              help='Generate Nomad environment variables')
    upload_parser.add_argument('--video-bucket', help='S3 bucket for videos (required with --generate-env)')
    upload_parser.add_argument('--output-bucket', help='S3 bucket for transcripts (required with --generate-env)')
    upload_parser.add_argument('--ollama-url', help='Ollama service URL (required with --generate-env)')
    upload_parser.add_argument('--hf-token', help='HuggingFace token')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Check job status')
    status_parser.add_argument('job_id', help='Job ID to check')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List all jobs')
    
    # Download command
    download_parser = subparsers.add_parser('download', help='Download results')
    download_parser.add_argument('job_id', help='Job ID to download results for')
    download_parser.add_argument('--output', help='Output file path (default: results-{job_id}.json)')
    
    # Create task command
    task_parser = subparsers.add_parser('create-task', help='Create tasks.json file with example content')
    task_parser.add_argument('--output', help='Output file path (default: <uuid>.json)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        if args.command == 'upload':
            upload_tasks(args)
        elif args.command == 'status':
            status(args)
        elif args.command == 'list':
            list_jobs(args)
        elif args.command == 'download':
            download_results(args)
        elif args.command == 'create-task':
            create_tasks(args)
            
    except Exception as e:
        logger.error(f"Command failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()