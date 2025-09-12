"""
Client for interacting with transcription containers in Nomad cluster.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Union
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import TranscriptionJob, TranscriptionResult, JobStatus

logger = logging.getLogger(__name__)


class TranscriptionClient:
    """Client for interacting with video transcription services."""
    
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize the transcription client.
        
        Args:
            base_url: Base URL of the transcription service
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        
        self.session = requests.Session()
        
        # Configure retries
        retry_strategy = Retry(
            total=max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "OPTIONS", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set headers
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'transcription-client/0.1.0'
        })
        
        if self.api_key:
            self.session.headers.update({'Authorization': f'Bearer {self.api_key}'})
    
    def submit_job(
        self,
        url: str,
        job_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> TranscriptionJob:
        """
        Submit a new transcription job.
        
        Args:
            url: URL of the video to transcribe
            job_id: Optional custom job ID (will generate UUID if not provided)
            metadata: Optional metadata to associate with the job
            
        Returns:
            TranscriptionJob object
        """
        if not job_id:
            job_id = str(uuid.uuid4())
        
        payload = {
            'job_id': job_id,
            'url': url,
            'metadata': metadata or {}
        }
        
        try:
            response = self.session.post(
                urljoin(self.base_url, '/api/v1/jobs'),
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            return TranscriptionJob(
                id=data['job_id'],
                url=data['url'],
                status=JobStatus(data['status']),
                created_at=datetime.fromisoformat(data['created_at']),
                metadata=data.get('metadata', {})
            )
            
        except requests.RequestException as e:
            logger.error(f"Failed to submit job: {e}")
            raise
    
    def get_job(self, job_id: str) -> TranscriptionJob:
        """
        Get job status and details.
        
        Args:
            job_id: ID of the job to retrieve
            
        Returns:
            TranscriptionJob object
        """
        try:
            response = self.session.get(
                urljoin(self.base_url, f'/api/v1/jobs/{job_id}'),
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            return TranscriptionJob(
                id=data['job_id'],
                url=data['url'],
                status=JobStatus(data['status']),
                created_at=datetime.fromisoformat(data['created_at']),
                updated_at=datetime.fromisoformat(data['updated_at']) if data.get('updated_at') else None,
                completed_at=datetime.fromisoformat(data['completed_at']) if data.get('completed_at') else None,
                error_message=data.get('error_message'),
                output_path=data.get('output_path'),
                metadata=data.get('metadata', {})
            )
            
        except requests.RequestException as e:
            logger.error(f"Failed to get job {job_id}: {e}")
            raise
    
    def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[TranscriptionJob]:
        """
        List transcription jobs.
        
        Args:
            status: Optional status filter
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip
            
        Returns:
            List of TranscriptionJob objects
        """
        params = {
            'limit': limit,
            'offset': offset
        }
        
        if status:
            params['status'] = status.value
        
        try:
            response = self.session.get(
                urljoin(self.base_url, '/api/v1/jobs'),
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            jobs = []
            
            for job_data in data['jobs']:
                job = TranscriptionJob(
                    id=job_data['job_id'],
                    url=job_data['url'],
                    status=JobStatus(job_data['status']),
                    created_at=datetime.fromisoformat(job_data['created_at']),
                    updated_at=datetime.fromisoformat(job_data['updated_at']) if job_data.get('updated_at') else None,
                    completed_at=datetime.fromisoformat(job_data['completed_at']) if job_data.get('completed_at') else None,
                    error_message=job_data.get('error_message'),
                    output_path=job_data.get('output_path'),
                    metadata=job_data.get('metadata', {})
                )
                jobs.append(job)
            
            return jobs
            
        except requests.RequestException as e:
            logger.error(f"Failed to list jobs: {e}")
            raise
    
    def get_result(self, job_id: str) -> TranscriptionResult:
        """
        Get the transcription result for a completed job.
        
        Args:
            job_id: ID of the completed job
            
        Returns:
            TranscriptionResult object
        """
        try:
            response = self.session.get(
                urljoin(self.base_url, f'/api/v1/jobs/{job_id}/result'),
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            return TranscriptionResult(
                job_id=data['job_id'],
                transcript=data['transcript'],
                segments=data['segments'],
                metadata=data['metadata'],
                duration=data['duration'],
                language=data.get('language')
            )
            
        except requests.RequestException as e:
            logger.error(f"Failed to get result for job {job_id}: {e}")
            raise
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running or pending job.
        
        Args:
            job_id: ID of the job to cancel
            
        Returns:
            True if job was cancelled successfully
        """
        try:
            response = self.session.delete(
                urljoin(self.base_url, f'/api/v1/jobs/{job_id}'),
                timeout=self.timeout
            )
            response.raise_for_status()
            return True
            
        except requests.RequestException as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            raise
    
    def health_check(self) -> Dict[str, str]:
        """
        Check the health of the transcription service.
        
        Returns:
            Health status dictionary
        """
        try:
            response = self.session.get(
                urljoin(self.base_url, '/health'),
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            logger.error(f"Health check failed: {e}")
            raise