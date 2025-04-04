import os
import logging
import base64
import shutil

# Set up logging
logger = logging.getLogger('discord')

# Define cookie paths in order of preference
cookie_paths = [
    os.path.join(os.getcwd(), 'cookies.txt'),
    '/app/cookies.txt',
    '/etc/railway/volume/cookies.txt',
    os.path.expanduser('~/.cookies.txt')
]

# Find existing cookie file
cookies_file = None
for path in cookie_paths:
    if os.path.exists(path) and os.path.getsize(path) > 0:
        cookies_file = path
        logger.info(f"Found cookies at: {cookies_file}")
        break

# If the cookie file is found but not in the current directory, copy it to the current directory
if cookies_file and cookies_file != os.path.join(os.getcwd(), 'cookies.txt'):
    try:
        local_path = os.path.join(os.getcwd(), 'cookies.txt')
        logger.info(f"Copying cookies from {cookies_file} to {local_path}")
        shutil.copy2(cookies_file, local_path)
        cookies_file = local_path
    except Exception as e:
        logger.error(f"Failed to copy cookies file: {str(e)}")

# Ensure we have a local cookies.txt file for yt-dlp to use
if not cookies_file:
    # Try to create cookie file from environment variable
    if 'COOKIES_BASE64' in os.environ and os.environ['COOKIES_BASE64']:
        try:
            cookies_file = os.path.join(os.getcwd(), 'cookies.txt')
            logger.info(f"Creating cookies file from COOKIES_BASE64 environment variable at {cookies_file}")
            
            try:
                with open(cookies_file, 'wb') as f:
                    cookies_data = os.environ['COOKIES_BASE64']
                    # Handle potential padding issues
                    missing_padding = len(cookies_data) % 4
                    if missing_padding:
                        cookies_data += '=' * (4 - missing_padding)
                    f.write(base64.b64decode(cookies_data))
                
                if os.path.exists(cookies_file) and os.path.getsize(cookies_file) > 0:
                    logger.info(f"Successfully created cookies file with size {os.path.getsize(cookies_file)} bytes")
                else:
                    logger.warning("Created cookies file is empty")
            except Exception as e:
                logger.error(f"Failed to write cookies file: {str(e)}")
                cookies_file = None
        except Exception as e:
            logger.error(f"Failed to decode COOKIES_BASE64: {str(e)}")
            cookies_file = None
    # If we have the cookie parts in our repo, try to reassemble them
    elif os.path.exists('cookie_part_ab') and os.path.exists('cookie_part_ac') and os.path.exists('cookie_part_ad') and os.path.exists('cookie_part_ae'):
        try:
            logger.info("Found cookie parts, attempting to reconstruct cookies.txt file")
            combined = ''
            for part in ['cookie_part_ab', 'cookie_part_ac', 'cookie_part_ad', 'cookie_part_ae']:
                with open(part, 'r') as f:
                    combined += f.read()
            
            cookies_file = os.path.join(os.getcwd(), 'cookies.txt')
            try:
                with open(cookies_file, 'wb') as f:
                    # Add the header if it's missing
                    if not combined.startswith('# Netscape HTTP Cookie File'):
                        combined = '# Netscape HTTP Cookie File\n# This file is generated by yt-dlp.  Do not edit.\n\n' + combined
                    f.write(combined.encode('utf-8'))
                
                if os.path.exists(cookies_file) and os.path.getsize(cookies_file) > 0:
                    logger.info(f"Successfully created cookies file with size {os.path.getsize(cookies_file)} bytes")
                else:
                    logger.warning("Created cookies file is empty")
            except Exception as e:
                logger.error(f"Failed to write cookies file: {str(e)}")
                cookies_file = None
        except Exception as e:
            logger.error(f"Failed to create cookies file from parts: {str(e)}")
            cookies_file = None

# Fallback - use the provided cookies.txt from the repository root
if not cookies_file and os.path.exists('cookies.txt'):
    cookies_file = os.path.join(os.getcwd(), 'cookies.txt')
    logger.info(f"Using existing cookies.txt file from repository root: {cookies_file}")

# Log cookie status
if cookies_file:
    logger.info(f"Using cookies file: {cookies_file}")
    # Ensure it's readable and has the right permissions
    try:
        os.chmod(cookies_file, 0o644)
    except Exception as e:
        logger.warning(f"Failed to set permissions on cookies file: {str(e)}")
else:
    logger.warning("No cookies file found or created - YouTube authentication may fail")

# YouTube DL configuration 
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'force-ipv4': True,
    'cachedir': False,
    'cookiefile': cookies_file,  # Use the found or created cookies file
    'no_color': True,
    'geo_bypass': True,
    'geo_bypass_country': 'US',
    'extract_flat': True,
    # Added options for better cookie handling
    'cookies': cookies_file,  # Explicit cookies parameter
    'skip_download': True,  # Don't download, just stream
    'extract_flat': 'in_playlist',
    'extractor_args': {
        'youtube': {
            'skip': ['dash', 'hls'],  # Skip DASH and HLS formats for better compatibility
        },
    }
}

# Log configuration
logger.info(f"YouTube-DL configuration initialized with format: {ytdl_format_options['format']}")
if cookies_file:
    logger.info(f"Using cookies from: {cookies_file}")
else:
    logger.warning("No cookies file specified, YouTube age-restricted content may not work")
