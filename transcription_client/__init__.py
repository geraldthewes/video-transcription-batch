"""
Transcription Client Package

A Python client library for interacting with video transcription containers
deployed in a Nomad cluster.
"""

__version__ = "0.1.0"
__author__ = "Gerald"

from .client import TranscriptionClient
from .models import TranscriptionJob, JobStatus

__all__ = ["TranscriptionClient", "TranscriptionJob", "JobStatus"]