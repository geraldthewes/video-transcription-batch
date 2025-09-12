"""
Data models for the transcription client.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any


class JobStatus(Enum):
    """Status of a transcription job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TranscriptionJob:
    """Represents a transcription job."""
    id: str
    url: str
    status: JobStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    output_path: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary representation."""
        return {
            "id": self.id,
            "url": self.url,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "output_path": self.output_path,
            "metadata": self.metadata or {}
        }


@dataclass
class TranscriptionResult:
    """Results from a completed transcription job."""
    job_id: str
    transcript: str
    segments: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    duration: float
    language: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary representation."""
        return {
            "job_id": self.job_id,
            "transcript": self.transcript,
            "segments": self.segments,
            "metadata": self.metadata,
            "duration": self.duration,
            "language": self.language
        }