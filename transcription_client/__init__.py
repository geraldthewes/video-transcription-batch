"""
Transcription Client Package

A Python client library for interacting with video transcription containers
deployed in a Nomad cluster.
"""

__version__ = "0.2.0"
__author__ = "Gerald"

from .client import TranscriptionClient
from .models import TranscriptionJob, JobStatus
from .s3_batch import S3BatchManager

__all__ = ["TranscriptionClient", "TranscriptionJob", "JobStatus", "S3BatchManager"]