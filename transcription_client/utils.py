"""
Utility functions for the transcription client.
"""

import re
import logging
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


def extract_video_id(url: str) -> str:
    """
    Extract video ID from YouTube URL.
    
    Args:
        url: YouTube URL
        
    Returns:
        Video ID string
        
    Raises:
        ValueError: If video ID cannot be extracted
    """
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/v/([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    raise ValueError(f"Could not extract video ID from URL: {url}")


def is_valid_youtube_url(url: str) -> bool:
    """
    Check if URL is a valid YouTube URL.
    
    Args:
        url: URL to validate
        
    Returns:
        True if URL is valid YouTube URL
    """
    try:
        extract_video_id(url)
        return True
    except ValueError:
        return False


def format_duration(seconds: float) -> str:
    """
    Format duration in seconds to human-readable format.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string (e.g., "1h 23m 45s")
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")
    
    return " ".join(parts)


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing invalid characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove multiple consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    
    # Remove leading/trailing underscores and spaces
    sanitized = sanitized.strip('_ ')
    
    # Ensure filename is not empty
    if not sanitized:
        sanitized = "unnamed"
    
    return sanitized


def parse_video_metadata(metadata: Dict) -> Dict:
    """
    Parse and clean video metadata.
    
    Args:
        metadata: Raw video metadata
        
    Returns:
        Cleaned metadata dictionary
    """
    cleaned = {}
    
    # Extract common fields
    if 'title' in metadata:
        cleaned['title'] = sanitize_filename(metadata['title'])
    
    if 'duration' in metadata:
        cleaned['duration'] = float(metadata['duration'])
        cleaned['duration_formatted'] = format_duration(metadata['duration'])
    
    if 'uploader' in metadata:
        cleaned['uploader'] = metadata['uploader']
    
    if 'upload_date' in metadata:
        cleaned['upload_date'] = metadata['upload_date']
    
    if 'view_count' in metadata:
        cleaned['view_count'] = metadata['view_count']
    
    if 'like_count' in metadata:
        cleaned['like_count'] = metadata['like_count']
    
    if 'description' in metadata:
        # Truncate description if too long
        description = metadata['description']
        if len(description) > 1000:
            description = description[:997] + "..."
        cleaned['description'] = description
    
    # Extract video quality info
    if 'height' in metadata:
        cleaned['resolution'] = f"{metadata.get('width', 'unknown')}x{metadata['height']}"
    
    if 'fps' in metadata:
        cleaned['fps'] = metadata['fps']
    
    if 'filesize' in metadata and metadata['filesize']:
        cleaned['filesize'] = metadata['filesize']
        cleaned['filesize_mb'] = round(metadata['filesize'] / (1024 * 1024), 2)
    
    return cleaned


def validate_config(config: Dict) -> List[str]:
    """
    Validate configuration dictionary.
    
    Args:
        config: Configuration to validate
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    # Required fields
    required_fields = ['base_url']
    for field in required_fields:
        if field not in config:
            errors.append(f"Missing required field: {field}")
    
    # Validate base_url format
    if 'base_url' in config:
        try:
            parsed = urlparse(config['base_url'])
            if not parsed.scheme or not parsed.netloc:
                errors.append("Invalid base_url format")
        except Exception:
            errors.append("Invalid base_url format")
    
    # Validate timeout
    if 'timeout' in config:
        try:
            timeout = float(config['timeout'])
            if timeout <= 0:
                errors.append("Timeout must be positive")
        except (ValueError, TypeError):
            errors.append("Invalid timeout value")
    
    # Validate max_retries
    if 'max_retries' in config:
        try:
            retries = int(config['max_retries'])
            if retries < 0:
                errors.append("max_retries cannot be negative")
        except (ValueError, TypeError):
            errors.append("Invalid max_retries value")
    
    return errors