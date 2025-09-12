"""
S3-based batch transcription manager for video transcription service.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


class S3BatchManager:
    """Manages batch transcription jobs using S3 for task/result storage."""
    
    def __init__(
        self,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_region: str = 'us-east-1',
        s3_endpoint: Optional[str] = None,
        tasks_bucket: Optional[str] = None,
        results_bucket: Optional[str] = None,
    ):
        """
        Initialize the S3 batch manager.
        
        Args:
            aws_access_key_id: AWS access key (uses env var if not provided)
            aws_secret_access_key: AWS secret key (uses env var if not provided) 
            aws_region: AWS region
            s3_endpoint: Custom S3 endpoint URL (optional)
            tasks_bucket: S3 bucket for tasks.json files
            results_bucket: S3 bucket for results.json files (defaults to tasks_bucket)
        """
        self.aws_region = aws_region
        self.s3_endpoint = s3_endpoint
        self.tasks_bucket = tasks_bucket or os.getenv('S3_TASKS_BUCKET')
        self.results_bucket = results_bucket or os.getenv('S3_RESULTS_BUCKET', self.tasks_bucket)
        
        # Setup S3 client
        session = boto3.Session(
            aws_access_key_id=aws_access_key_id or os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=aws_secret_access_key or os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=aws_region
        )
        
        s3_kwargs = {}
        if s3_endpoint:
            s3_kwargs['endpoint_url'] = s3_endpoint
        
        self.s3_client = session.client('s3', **s3_kwargs)
        
        if not self.tasks_bucket:
            raise ValueError("tasks_bucket must be provided or S3_TASKS_BUCKET env var must be set")
    
    def upload_tasks(self, tasks: List[Dict[str, Any]], job_id: Optional[str] = None) -> str:
        """
        Upload tasks to S3 and return the job ID.
        
        Args:
            tasks: List of task dictionaries (video URL, title, description, etc.)
            job_id: Optional job ID (will generate UUID if not provided)
            
        Returns:
            Job ID for the uploaded tasks
        """
        if not job_id:
            job_id = str(uuid.uuid4())
        
        # Validate tasks
        if not isinstance(tasks, list):
            raise ValueError("Tasks must be a list")
        
        for task in tasks:
            if not isinstance(task, dict) or 'url' not in task:
                raise ValueError("Each task must be a dict with 'url' field")
        
        # Upload tasks to S3
        tasks_key = f"jobs/{job_id}/tasks.json"
        
        try:
            tasks_json = json.dumps(tasks, indent=2, ensure_ascii=False)
            self.s3_client.put_object(
                Bucket=self.tasks_bucket,
                Key=tasks_key,
                Body=tasks_json.encode('utf-8'),
                ContentType='application/json'
            )
            
            logger.info(f"Uploaded {len(tasks)} tasks to s3://{self.tasks_bucket}/{tasks_key}")
            return job_id
            
        except Exception as e:
            logger.error(f"Failed to upload tasks to S3: {e}")
            raise
    
    def download_tasks(self, job_id: str) -> List[Dict[str, Any]]:
        """
        Download tasks from S3 for a given job ID.
        
        Args:
            job_id: Job ID to download tasks for
            
        Returns:
            List of task dictionaries
        """
        tasks_key = f"jobs/{job_id}/tasks.json"
        
        try:
            response = self.s3_client.get_object(Bucket=self.tasks_bucket, Key=tasks_key)
            tasks_json = response['Body'].read().decode('utf-8')
            tasks = json.loads(tasks_json)
            
            logger.info(f"Downloaded {len(tasks)} tasks from s3://{self.tasks_bucket}/{tasks_key}")
            return tasks
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise FileNotFoundError(f"Tasks file not found: s3://{self.tasks_bucket}/{tasks_key}")
            else:
                logger.error(f"Failed to download tasks: {e}")
                raise
        except Exception as e:
            logger.error(f"Failed to parse tasks JSON: {e}")
            raise
    
    def download_results(self, job_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Download results from S3 for a given job ID.
        
        Args:
            job_id: Job ID to download results for
            
        Returns:
            List of result dictionaries, or None if not found
        """
        results_key = f"jobs/{job_id}/results.json"
        
        try:
            response = self.s3_client.get_object(Bucket=self.results_bucket, Key=results_key)
            results_json = response['Body'].read().decode('utf-8')
            results = json.loads(results_json)
            
            logger.info(f"Downloaded {len(results)} results from s3://{self.results_bucket}/{results_key}")
            return results
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.info(f"Results file not found: s3://{self.results_bucket}/{results_key}")
                return None
            else:
                logger.error(f"Failed to download results: {e}")
                raise
        except Exception as e:
            logger.error(f"Failed to parse results JSON: {e}")
            raise
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get the status of a transcription job.
        
        Args:
            job_id: Job ID to check status for
            
        Returns:
            Dictionary with job status information
        """
        results = self.download_results(job_id)
        
        if not results:
            return {
                'job_id': job_id,
                'status': 'pending',
                'total_tasks': 0,
                'completed_tasks': 0,
                'failed_tasks': 0,
                'skipped_tasks': 0,
                'progress': 0.0
            }
        
        total_tasks = len(results)
        completed_tasks = sum(1 for r in results if r.get('status') == 'success')
        failed_tasks = sum(1 for r in results if r.get('status') == 'failed')
        skipped_tasks = sum(1 for r in results if r.get('status') == 'skipped')
        processing_tasks = sum(1 for r in results if r.get('status') == 'processing')
        
        progress = (completed_tasks + failed_tasks + skipped_tasks) / total_tasks if total_tasks > 0 else 0.0
        
        if processing_tasks > 0:
            overall_status = 'processing'
        elif completed_tasks + skipped_tasks == total_tasks:
            overall_status = 'completed'
        elif failed_tasks > 0:
            overall_status = 'partial_failure'
        else:
            overall_status = 'pending'
        
        return {
            'job_id': job_id,
            'status': overall_status,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'failed_tasks': failed_tasks,
            'skipped_tasks': skipped_tasks,
            'processing_tasks': processing_tasks,
            'progress': progress
        }
    
    def list_jobs(self) -> List[str]:
        """
        List all job IDs in the tasks bucket.
        
        Returns:
            List of job ID strings
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.tasks_bucket,
                Prefix='jobs/',
                Delimiter='/'
            )
            
            job_ids = []
            for prefix in response.get('CommonPrefixes', []):
                job_path = prefix['Prefix']  # e.g., 'jobs/uuid/
                job_id = job_path.strip('/').split('/')[-1]
                if job_id:
                    job_ids.append(job_id)
            
            return sorted(job_ids)
            
        except Exception as e:
            logger.error(f"Failed to list jobs: {e}")
            raise
    
    def create_nomad_env_vars(
        self,
        job_id: str,
        video_bucket: str,
        output_bucket: str,
        ollama_url: str,
        hf_token: Optional[str] = None,
        **kwargs
    ) -> Dict[str, str]:
        """
        Create environment variables for Nomad job.
        
        Args:
            job_id: Job ID for S3 tasks/results
            video_bucket: S3 bucket for storing downloaded videos
            output_bucket: S3 bucket for storing transcription outputs
            ollama_url: URL of Ollama service
            hf_token: HuggingFace token (optional)
            **kwargs: Additional environment variables
            
        Returns:
            Dictionary of environment variables
        """
        env_vars = {
            'USE_S3_CONFIG': 'true',
            'S3_TASKS_BUCKET': self.tasks_bucket,
            'S3_TASKS_KEY': f'jobs/{job_id}/tasks.json',
            'S3_RESULTS_BUCKET': self.results_bucket,
            'S3_RESULTS_KEY': f'jobs/{job_id}/results.json',
            'S3_VIDEO_BUCKET': video_bucket,
            'S3_OUTPUT_BUCKET': output_bucket,
            'OLLAMA_URL': ollama_url,
            'SPEAKER_DIARIZATION': 'true',
            'AWS_REGION': self.aws_region,
        }
        
        if self.s3_endpoint:
            env_vars['S3_ENDPOINT'] = self.s3_endpoint
            
        if hf_token:
            env_vars['HF_TOKEN'] = hf_token
        
        # Add any additional environment variables
        env_vars.update(kwargs)
        
        return env_vars
    
    def save_tasks_file(self, tasks: List[Dict[str, Any]], file_path: str):
        """
        Save tasks to a local JSON file.
        
        Args:
            tasks: List of task dictionaries
            file_path: Path to save the JSON file
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(tasks)} tasks to {file_path}")
    
    def load_tasks_file(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Load tasks from a local JSON file.
        
        Args:
            file_path: Path to the JSON file
            
        Returns:
            List of task dictionaries
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            tasks = json.load(f)
        
        if not isinstance(tasks, list):
            raise ValueError("Tasks file must contain a JSON array")
        
        logger.info(f"Loaded {len(tasks)} tasks from {file_path}")
        return tasks