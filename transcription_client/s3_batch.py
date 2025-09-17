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
        aws_profile: Optional[str] = None,
        s3_endpoint: Optional[str] = None,
        transcriber_bucket: Optional[str] = None,
        transcriber_prefix: str = '',
    ):
        """
        Initialize the S3 batch manager.
        
        Args:
            aws_access_key_id: AWS access key (uses env var if not provided)
            aws_secret_access_key: AWS secret key (uses env var if not provided) 
            aws_region: AWS region
            aws_profile: AWS profile name for credentials (uses ~/.aws/credentials)
            s3_endpoint: Custom S3 endpoint URL (optional)
            transcriber_bucket: S3 bucket for all transcription data
            transcriber_prefix: S3 prefix for organizing transcription jobs
        """
        self.aws_region = aws_region
        self.s3_endpoint = s3_endpoint
        self.transcriber_bucket = transcriber_bucket or os.getenv('S3_TRANSCRIBER_BUCKET')
        self.transcriber_prefix = transcriber_prefix or os.getenv('S3_TRANSCRIBER_PREFIX', '')
        
        # Ensure prefix ends with / if not empty
        if self.transcriber_prefix and not self.transcriber_prefix.endswith('/'):
            self.transcriber_prefix += '/'
        
        # Setup S3 client
        session_kwargs = {
            'region_name': aws_region
        }
        
        # Use profile if specified, otherwise use explicit credentials or env vars
        if aws_profile:
            session_kwargs['profile_name'] = aws_profile
        else:
            session_kwargs['aws_access_key_id'] = aws_access_key_id or os.getenv('AWS_ACCESS_KEY_ID')
            session_kwargs['aws_secret_access_key'] = aws_secret_access_key or os.getenv('AWS_SECRET_ACCESS_KEY')
        
        session = boto3.Session(**session_kwargs)
        
        s3_kwargs = {}
        if s3_endpoint:
            s3_kwargs['endpoint_url'] = s3_endpoint
        
        self.s3_client = session.client('s3', **s3_kwargs)
        
        if not self.transcriber_bucket:
            raise ValueError("transcriber_bucket must be provided or S3_TRANSCRIBER_BUCKET env var must be set")
    
    def upload_tasks(self, tasks: List[Dict[str, Any]], job_id: Optional[str] = None, transcription_config: Optional[Dict[str, Any]] = None, resource_config: Optional[Dict[str, Any]] = None) -> str:
        """
        Upload tasks to S3 and return the job ID.

        Args:
            tasks: List of task dictionaries (video URL, title, description, etc.)
            job_id: Optional job ID (will generate UUID if not provided)
            transcription_config: Optional transcription configuration parameters
            resource_config: Optional resource allocation configuration (cpu, memory, gpu_count)

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
        tasks_key = f"{self.transcriber_prefix}{job_id}/tasks.json"
        
        try:
            tasks_json = json.dumps(tasks, indent=2, ensure_ascii=False)
            self.s3_client.put_object(
                Bucket=self.transcriber_bucket,
                Key=tasks_key,
                Body=tasks_json.encode('utf-8'),
                ContentType='application/json'
            )
            
            # Upload transcription config if provided
            if transcription_config:
                config_key = f"{self.transcriber_prefix}{job_id}/config.json"
                config_json = json.dumps(transcription_config, indent=2, ensure_ascii=False)
                self.s3_client.put_object(
                    Bucket=self.transcriber_bucket,
                    Key=config_key,
                    Body=config_json.encode('utf-8'),
                    ContentType='application/json'
                )
                logger.info(f"Uploaded transcription config to s3://{self.transcriber_bucket}/{config_key}")

            # Upload resource config if provided
            if resource_config:
                resource_key = f"{self.transcriber_prefix}{job_id}/resources.json"
                resource_json = json.dumps(resource_config, indent=2, ensure_ascii=False)
                self.s3_client.put_object(
                    Bucket=self.transcriber_bucket,
                    Key=resource_key,
                    Body=resource_json.encode('utf-8'),
                    ContentType='application/json'
                )
                logger.info(f"Uploaded resource config to s3://{self.transcriber_bucket}/{resource_key}")

            logger.info(f"Uploaded {len(tasks)} tasks to s3://{self.transcriber_bucket}/{tasks_key}")
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
        tasks_key = f"{self.transcriber_prefix}{job_id}/tasks.json"
        
        try:
            response = self.s3_client.get_object(Bucket=self.transcriber_bucket, Key=tasks_key)
            tasks_json = response['Body'].read().decode('utf-8')
            tasks = json.loads(tasks_json)
            
            logger.info(f"Downloaded {len(tasks)} tasks from s3://{self.transcriber_bucket}/{tasks_key}")
            return tasks
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise FileNotFoundError(f"Tasks file not found: s3://{self.transcriber_bucket}/{tasks_key}")
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
        results_key = f"{self.transcriber_prefix}{job_id}/results.json"
        
        try:
            response = self.s3_client.get_object(Bucket=self.transcriber_bucket, Key=results_key)
            results_json = response['Body'].read().decode('utf-8')
            results = json.loads(results_json)
            
            logger.info(f"Downloaded {len(results)} results from s3://{self.transcriber_bucket}/{results_key}")
            return results
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.info(f"Results file not found: s3://{self.transcriber_bucket}/{results_key}")
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
                Bucket=self.transcriber_bucket,
                Prefix=self.transcriber_prefix,
                Delimiter='/'
            )
            
            job_ids = []
            for prefix in response.get('CommonPrefixes', []):
                job_path = prefix['Prefix']  # e.g., 'prefix/uuid/'
                # Remove the transcriber_prefix and trailing slash to get job_id
                job_id = job_path.replace(self.transcriber_prefix, '').strip('/')
                if job_id:
                    job_ids.append(job_id)
            
            return sorted(job_ids)
            
        except Exception as e:
            logger.error(f"Failed to list jobs: {e}")
            raise
    
    def create_nomad_env_vars(
        self,
        job_id: str,
        ollama_url: str,
        hf_token: Optional[str] = None,
        **kwargs
    ) -> Dict[str, str]:
        """
        Create environment variables for Nomad job.
        
        Args:
            job_id: Job ID for S3 job directory  
            ollama_url: URL of Ollama service
            hf_token: HuggingFace token (optional)
            **kwargs: Additional environment variables
            
        Returns:
            Dictionary of environment variables
        """
        env_vars = {
            'S3_TRANSCRIBER_BUCKET': self.transcriber_bucket,
            'S3_TRANSCRIBER_PREFIX': self.transcriber_prefix,
            'S3_JOB_ID': job_id,
            'OLLAMA_URL': ollama_url,
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
    
    def download_config(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Download transcription configuration from S3 for a given job ID.
        
        Args:
            job_id: Job ID to download config for
            
        Returns:
            Configuration dictionary, or None if not found
        """
        config_key = f"{self.transcriber_prefix}{job_id}/config.json"
        
        try:
            response = self.s3_client.get_object(Bucket=self.transcriber_bucket, Key=config_key)
            config_json = response['Body'].read().decode('utf-8')
            config = json.loads(config_json)
            
            logger.info(f"Downloaded transcription config from s3://{self.transcriber_bucket}/{config_key}")
            return config
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.info(f"Config file not found: s3://{self.transcriber_bucket}/{config_key}")
                return None
            else:
                logger.error(f"Failed to download config: {e}")
                raise
        except Exception as e:
            logger.error(f"Failed to parse config JSON: {e}")
            raise

    def download_resource_config(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Download resource configuration from S3 for a given job ID.

        Args:
            job_id: Job ID to download resource config for

        Returns:
            Resource configuration dictionary, or None if not found
        """
        resource_key = f"{self.transcriber_prefix}{job_id}/resources.json"

        try:
            response = self.s3_client.get_object(Bucket=self.transcriber_bucket, Key=resource_key)
            resource_json = response['Body'].read().decode('utf-8')
            resource_config = json.loads(resource_json)

            logger.info(f"Downloaded resource config from s3://{self.transcriber_bucket}/{resource_key}")
            return resource_config

        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.info(f"Resource config file not found: s3://{self.transcriber_bucket}/{resource_key}")
                return None
            else:
                logger.error(f"Failed to download resource config: {e}")
                raise
        except Exception as e:
            logger.error(f"Failed to parse resource config JSON: {e}")
            raise