import asyncio
from async_timeout import timeout
import discord
import yt_dlp
import logging
import re
import os
import glob
import shutil
from typing import Optional, Dict, Any
from ytdl_config import ytdl_format_options

# Set up logging
logger = logging.getLogger('discord')

# Suppress yt-dlp bug reports
yt_dlp.utils.bug_reports_message = lambda: ''

# Find FFmpeg in various locations
def find_ffmpeg_path():
    """Find ffmpeg executable path"""
    ffmpeg_paths = [
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        'ffmpeg'
    ]
    
    # Check Nix store paths
    try:
        nix_paths = glob.glob('/nix/store/*/ffmpeg-*/bin/ffmpeg')
        if nix_paths:
            ffmpeg_paths.extend(nix_paths)
    except Exception:
        pass
    
    # Check if ffmpeg is in PATH
    ffmpeg_in_path = shutil.which('ffmpeg')
    if ffmpeg_in_path:
        ffmpeg_paths.append(ffmpeg_in_path)
    
    for path in ffmpeg_paths:
        if os.path.exists(path):
            logger.info(f"Found ffmpeg at: {path}")
            return path
    
    # Last resort, just return the command and hope it's in PATH
    logger.warning("FFmpeg not found in common paths, using 'ffmpeg' as fallback")
    return 'ffmpeg'

# FFMPEG Configuration - optimized for low-latency and high-quality audio
ffmpeg_options = {
    'options': '-vn -b:a 192k -bufsize 192k -ac 2',  # Simplified options for better compatibility
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -analyzeduration 0 -probesize 1M',
    'executable': 'ffmpeg'  # Use system ffmpeg for Railway compatibility
}

# Load opus
def try_load_opus():
    """Try to load Opus from various library paths"""
    opus_libs = ['libopus.so.0', 'libopus.so.1', 'libopus.0.dylib', 'libopus.dylib', 'opus']
    
    if discord.opus.is_loaded():
        logger.info("Opus is already loaded")
        return True
        
    for lib in opus_libs:
        try:
            discord.opus.load_opus(lib)
            logger.info(f"Successfully loaded opus library: {lib}")
            return True
        except Exception as e:
            logger.debug(f"Failed to load opus library {lib}: {str(e)}")
            continue
    
    logger.warning("Could not load any opus library. Audio quality may be reduced.")
    return False

# Try to load opus on module import
opus_loaded = try_load_opus()

# Create yt-dlp instance with configuration
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)
logger.info(f"Initialized yt-dlp with cookies from: {ytdl_format_options.get('cookiefile', 'No cookies file specified')}")

def is_url(text: str) -> bool:
    """Check if the text is a URL"""
    # More permissive URL pattern to handle YouTube and other streaming links
    url_pattern = re.compile(
        r'^https?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,}\.?|'  # Changed {2,6} to {2,} to allow longer TLDs
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?].*)$', re.IGNORECASE)  # Changed \S+ to .* to allow more characters
    
    # Also check for youtu.be short links
    youtube_short = re.compile(r'^https?://youtu\.be/[a-zA-Z0-9_-]+', re.IGNORECASE)
    
    return bool(url_pattern.match(text) or youtube_short.match(text))

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source: discord.FFmpegPCMAudio, *, data: Dict[str, Any], volume: float = 0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title', 'Unknown title')
        self.url = data.get('url', 'Unknown URL')
        self.duration = int(data.get('duration', 0))
        self.thumbnail = data.get('thumbnail', None)
        self.webpage_url = data.get('webpage_url', None)

    @classmethod
    async def from_url(cls, url: str, *, loop: Optional[asyncio.AbstractEventLoop] = None) -> 'YTDLSource':
        """Create a YTDLSource from a URL or search query"""
        loop = loop or asyncio.get_event_loop()
        
        try:
            logger.info(f"Processing {'URL' if is_url(url) else 'search query'}: {url}")
            
            # If not a URL, search on YouTube
            if not is_url(url):
                url = f"ytsearch:{url}"

            # Extract audio info with proper error handling
            try:
                # Use a backup method if the first extraction fails
                data = None
                error_msg = None
                
                # First attempt with standard options
                try:
                    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
                except Exception as e:
                    error_msg = str(e)
                    logger.warning(f"First extraction attempt failed: {error_msg}")
                
                # If first attempt failed, try without geo-bypass
                if not data:
                    try:
                        alt_options = ytdl_format_options.copy()
                        alt_options.pop('geo_bypass', None)
                        alt_options.pop('geo_bypass_country', None)
                        
                        with yt_dlp.YoutubeDL(alt_options) as alt_ytdl:
                            data = await loop.run_in_executor(None, lambda: alt_ytdl.extract_info(url, download=False))
                    except Exception as e:
                        logger.warning(f"Second extraction attempt failed: {str(e)}")
                        # If both attempts failed, raise the original error
                        if error_msg:
                            raise Exception(error_msg)
                        raise
                
                # Process the entries if any
                if 'entries' in data:
                    data = data['entries'][0]

                if not data:
                    raise Exception("Could not find any matching songs.")

                # Get the direct audio URL
                filename = data['url']
                logger.info(f"Successfully extracted audio URL for: {data.get('title', 'Unknown')}")
                
                # Create audio source
                source = discord.FFmpegPCMAudio(filename, **ffmpeg_options)
                return cls(source, data=data)
            except yt_dlp.utils.ExtractorError as e:
                error_msg = str(e)
                if "Sign in to confirm" in error_msg or "Please sign in" in error_msg:
                    logger.error("YouTube auth error detected!")
                    
                    # Check cookie file
                    cookie_path = ytdl_format_options.get('cookiefile', 'cookies.txt')
                    logger.error(f"Cookie path: {cookie_path}")
                    
                    cookie_exists = os.path.exists(cookie_path) if cookie_path else False
                    logger.error(f"Cookie exists: {cookie_exists}")
                    
                    # Log info about cookies file
                    if cookie_exists:
                        cookie_size = os.path.getsize(cookie_path)
                        logger.error(f"Cookie file size: {cookie_size} bytes")
                        
                        # Try to read first few lines of cookies file for debugging
                        try:
                            with open(cookie_path, 'r') as f:
                                first_lines = [next(f) for _ in range(3)]
                                logger.error(f"First lines of cookie file: {first_lines}")
                        except Exception as err:
                            logger.error(f"Error reading cookie file: {str(err)}")
                    
                    # Try another approach with browser cookies
                    logger.error("Trying alternative approach with explicit cookies path...")
                    try:
                        alt_options = ytdl_format_options.copy()
                        # Make sure we have a valid cookies file path in the current directory
                        local_cookie = os.path.join(os.getcwd(), 'cookies.txt')
                        if os.path.exists(local_cookie) and os.path.getsize(local_cookie) > 0:
                            alt_options['cookiefile'] = local_cookie
                            
                            with yt_dlp.YoutubeDL(alt_options) as alt_ytdl:
                                data = alt_ytdl.extract_info(url, download=False)
                                
                                if 'entries' in data:
                                    data = data['entries'][0]
                                
                                if data:
                                    logger.info(f"Successfully extracted with alternative cookies approach: {data.get('title', 'Unknown')}")
                                    filename = data['url']
                                    source = discord.FFmpegPCMAudio(filename, **ffmpeg_options)
                                    return cls(source, data=data)
                    except Exception as alt_err:
                        logger.error(f"Alternative cookies approach failed: {str(alt_err)}")
                    
                    # If we get here, both approaches failed
                    if not cookie_exists:
                        raise Exception("Cookies file not found. Please add a valid cookies.txt file.")
                    elif cookie_exists and os.path.getsize(cookie_path) == 0:
                        raise Exception("Cookies file is empty. Please add valid cookies.")
                    else:
                        raise Exception("YouTube requires authentication. Your cookies might be expired or invalid. Try exporting new cookies from Opera GX.")
                
                # If it's not a cookie error, re-raise the original exception
                raise
        except Exception as e:
            logger.error(f"Error extracting info: {str(e)}", exc_info=True)
            raise

class MusicPlayer:
    def __init__(self, bot, ctx):
        self.bot = bot
        self.ctx = ctx
        self.queue = []
        self.current = None
        self.next = asyncio.Event()
        self.audio_player = bot.loop.create_task(self.player_loop())
        self.volume = 0.5
        logger.info(f"Music player initialized for guild: {ctx.guild.id}")

    async def player_loop(self):
        """Main player loop for handling the queue"""
        await self.bot.wait_until_ready()
        
        while True:
            self.next.clear()

            try:
                # Wait for a song if queue is empty
                if not self.queue:
                    try:
                        logger.info("Queue empty, waiting for new tracks...")
                        async with timeout(300):  # 5 minute timeout
                            await self.next.wait()
                    except asyncio.TimeoutError:
                        logger.info("Player inactive for 5 minutes, cleaning up...")
                        return await self.cleanup()

                # Play next song in queue
                if self.queue:
                    self.current = self.queue.pop(0)
                    logger.info(f"Playing next track: {self.current['title']}")
                    
                    try:
                        # Determine whether to use PCMVolumeTransformer or fallback
                        use_fallback = not discord.opus.is_loaded()
                        song_title = self.current['title']

                        if not use_fallback:
                            # Try using YTDLSource with volume control
                            try:
                                source = await YTDLSource.from_url(self.current['url'], loop=self.bot.loop)
                                song_title = source.title
                                source.volume = self.volume
                                self.ctx.voice_client.play(
                                    source,
                                    after=lambda e: self.bot.loop.call_soon_threadsafe(self._song_finished, e)
                                )
                            except discord.opus.OpusNotLoaded:
                                use_fallback = True
                                logger.warning("Opus not loaded, falling back to basic FFmpegPCMAudio")
                        
                        if use_fallback:
                            # Fallback to direct FFmpeg audio without volume control
                            data = await self.bot.loop.run_in_executor(
                                None, 
                                lambda: ytdl.extract_info(self.current['url'], download=False)
                            )
                            if 'entries' in data:
                                data = data['entries'][0]

                            song_title = data.get('title', self.current['title'])
                            filename = data['url']
                            audio_source = discord.FFmpegPCMAudio(filename, **ffmpeg_options)
                            self.ctx.voice_client.play(
                                audio_source,
                                after=lambda e: self.bot.loop.call_soon_threadsafe(self._song_finished, e)
                            )
                            
                            await self.ctx.send("⚠️ Using fallback audio player (volume control unavailable)")

                        await self.ctx.send(f"🎵 Now playing: **{song_title}**")
                        logger.info(f"Now playing: {song_title}")

                    except Exception as e:
                        logger.error(f"Error playing track: {str(e)}", exc_info=True)
                        await self.ctx.send(f"❌ Error playing track: {str(e)}")
                        self._song_finished(None)
                        continue

                await self.next.wait()

            except Exception as e:
                logger.error(f"Error in player loop: {str(e)}", exc_info=True)
                await asyncio.sleep(1)
                continue

    def _song_finished(self, error):
        """Callback for when a song finishes playing"""
        if error:
            logger.error(f"Error in audio playback: {error}")
        
        self.bot.loop.call_soon_threadsafe(self.next.set)

    async def add_to_queue(self, query: str) -> Dict[str, Any]:
        """Add a song to the queue"""
        try:
            logger.info(f"Processing query: {query}")
            
            # Clean the query to improve search results
            if not is_url(query):
                # Remove parentheses and trim whitespace
                cleaned_query = query.replace('(', '').replace(')', '').strip()
                query = f"ytsearch:{cleaned_query}"

            # Extract song information
            try:
                data = await self.bot.loop.run_in_executor(
                    None,
                    lambda: ytdl.extract_info(query, download=False)
                )
                
                if 'entries' in data:
                    data = data['entries'][0]

                if not data:
                    raise Exception("Could not find any matching songs.")
                
                # Process duration
                duration = data.get('duration')
                if duration is None:
                    duration = 0
                elif isinstance(duration, str):
                    try:
                        duration = int(duration)
                    except ValueError:
                        duration = 0

                # Create song info dictionary
                song_info = {
                    'url': data.get('url', data.get('webpage_url')),
                    'title': data.get('title', 'Unknown title'),
                    'duration': duration,
                    'webpage_url': data.get('webpage_url', None),
                    'thumbnail': data.get('thumbnail', None),
                    'requester': self.ctx.author.name
                }

                # Add to queue and signal player if needed
                self.queue.append(song_info)
                logger.info(f"Added to queue: {song_info['title']}")

                if not self.ctx.voice_client.is_playing():
                    self.next.set()

                return song_info
                
            except Exception as e:
                logger.error(f"Error extracting song info: {str(e)}", exc_info=True)
                if "Sign in to confirm" in str(e) or "Please sign in" in str(e):
                    raise Exception("YouTube requires authentication. Please check your cookies.txt file.")
                raise Exception(f"Could not process {query}: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}", exc_info=True)
            raise Exception(f"Could not process {query}: {str(e)}")

    async def skip(self) -> None:
        """Skip the current song"""
        if self.ctx.voice_client and self.ctx.voice_client.is_playing():
            logger.info("Skipping current track")
            self.ctx.voice_client.stop()

    async def stop(self) -> None:
        """Stop playing and clear the queue"""
        logger.info("Stopping playback and clearing queue")
        self.queue.clear()
        if self.ctx.voice_client and self.ctx.voice_client.is_playing():
            self.ctx.voice_client.stop()

    async def cleanup(self) -> None:
        """Clean up player resources"""
        try:
            logger.info("Cleaning up player resources")
            self.queue.clear()
            if hasattr(self, 'audio_player') and not self.audio_player.cancelled():
                self.audio_player.cancel()
            if self.ctx.voice_client:
                await self.ctx.voice_client.disconnect()
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}", exc_info=True)

    def set_volume(self, volume: float) -> None:
        """Set the volume of the player"""
        self.volume = max(0.0, min(1.0, volume))
        if self.ctx.voice_client and hasattr(self.ctx.voice_client, 'source') and self.ctx.voice_client.source:
            self.ctx.voice_client.source.volume = self.volume
            logger.info(f"Volume set to {self.volume*100}%")
    
    def is_url(self, text: str) -> bool:
        """Check if the text is a URL"""
        return is_url(text)
