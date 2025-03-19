from typing import Dict, Any
import logging

logger = logging.getLogger('utils')

def format_duration(duration: int) -> str:
    """Format duration in seconds to MM:SS or HH:MM:SS format"""
    if not duration:
        return "00:00"

    hours = duration // 3600
    minutes = (duration % 3600) // 60
    seconds = duration % 60

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"

async def get_track_info(track: Dict[str, Any]) -> Dict[str, Any]:
    """Get formatted track information"""
    try:
        return {
            'title': track.get('title', 'Unknown title'),
            'duration': format_duration(track.get('duration', 0)),
            'requester': track.get('requester', 'Unknown'),
            'thumbnail': track.get('thumbnail'),
            'webpage_url': track.get('webpage_url')
        }
    except Exception as e:
        logger.error(f"Error formatting track info: {str(e)}")
        return {
            'title': 'Unknown track',
            'duration': '00:00',
            'requester': 'Unknown',
            'thumbnail': None,
            'webpage_url': None
        }

def check_cookies_file(path: str) -> bool:
    """Check if cookies file exists and is not empty"""
    import os
    try:
        return os.path.exists(path) and os.path.getsize(path) > 0
    except Exception:
        return False

def format_uptime(seconds: int) -> str:
    """Format seconds into a human-readable uptime string"""
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    
    return " ".join(parts)
