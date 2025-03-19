import discord
from discord.ext import commands, tasks
import os
import logging
import asyncio
import time
import aiohttp
import json
from music_player import MusicPlayer, find_ffmpeg_path
from utils import format_duration, get_track_info
import contextlib

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('discord')

# Global variables
bot_online = False
bot_connected = False
start_time = time.time()
status_callback = None

# Bot statistics
stats = {
    "play_count": 0,
    "errors": 0,
    "reconnections": 0,
    "commands_used": {}
}

class RadioFMBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True
        
        super().__init__(command_prefix='!', intents=intents)
        self.music_players = {}
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5
        self.start_time = time.time()
        self.ffmpeg_path = find_ffmpeg_path()

    async def setup_hook(self):
        await self.add_cog(MusicCommands(self))
        # Start background tasks
        self.check_voice_connections.start()
        self.heartbeat.start()
        self.update_status.start()
        logger.info(f"Bot setup completed. FFmpeg path: {self.ffmpeg_path}")
        
        # Report FFmpeg status
        if self.ffmpeg_path:
            await self.report_status(ffmpeg_status="available")
        else:
            await self.report_status(ffmpeg_status="not_found")

    @tasks.loop(seconds=30)
    async def heartbeat(self):
        """Send heartbeat to maintain connection"""
        try:
            logger.info("Bot heartbeat - Status: Online")
            self.reconnect_attempts = 0
            self.reconnect_delay = 5
            await self.report_status(status="online")
            global bot_online
            bot_online = True
        except Exception as e:
            logger.error(f"Heartbeat error: {str(e)}", exc_info=True)
            await self.report_status(status="error")

    @tasks.loop(minutes=1)
    async def check_voice_connections(self):
        """Check and maintain voice connections"""
        try:
            # Count active voice connections
            active_connections = len(self.voice_clients)
            await self.report_status(voice_connections=active_connections)
            
            # Create a list of items to avoid dictionary modification during iteration
            players = list(self.music_players.items())
            for guild_id, player in players:
                if not player.ctx.voice_client or not player.ctx.voice_client.is_connected():
                    logger.warning(f"Lost voice connection in guild {guild_id}, attempting to reconnect...")
                    try:
                        await player.cleanup()
                        self.music_players.pop(guild_id, None)
                    except Exception as e:
                        logger.error(f"Error cleaning up player: {str(e)}", exc_info=True)
        except Exception as e:
            logger.error(f"Error checking voice connections: {str(e)}", exc_info=True)

    @tasks.loop(minutes=5)
    async def update_status(self):
        """Periodically update bot status"""
        try:
            await self.change_presence(activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="!help for commands"
            ))
            
            # Report statistics
            await self.report_status(
                status="online", 
                discord_connection="connected",
                play_count=stats["play_count"]
            )
        except Exception as e:
            logger.error(f"Error updating status: {str(e)}", exc_info=True)

    async def on_ready(self):
        try:
            logger.info(f'Bot is ready! Logged in as {self.user.name}')
            global bot_connected
            bot_connected = True
            
            # Try to set username if not already "Radio FM"
            if self.user.name != "Radio FM":
                try:
                    await self.user.edit(username="Radio FM")
                    logger.info(f"Successfully updated bot username to Radio FM")
                except discord.HTTPException as e:
                    if e.code == 50035:  # Rate limit error
                        logger.warning(f"Could not update username - rate limited. Current name: {self.user.name}")
                    else:
                        logger.error(f"Failed to update bot profile: {str(e)}")
            
            await self.change_presence(activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="!help for commands"
            ))
            
            await self.report_status(
                status="online",
                discord_connection="connected"
            )
        except Exception as e:
            logger.error(f"Error in on_ready: {str(e)}")
            await self.report_status(status="error", last_error=str(e))

    async def on_error(self, event, *args, **kwargs):
        logger.error(f'Error in {event}', exc_info=True)
        stats["errors"] += 1
        await self.report_status(last_error=f"Error in {event}")

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send("❌ Command not found. Type `!help` for a list of commands.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing required argument: {error.param.name}")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Invalid argument provided.")
        else:
            logger.error(f"Command error: {str(error)}", exc_info=True)
            await ctx.send(f"❌ An error occurred: {str(error)}")
            await self.report_status(last_error=f"Command error: {str(error)}")

    async def on_disconnect(self):
        """Handle Discord disconnections with exponential backoff"""
        global bot_connected
        bot_connected = False
        self.reconnect_attempts += 1
        stats["reconnections"] += 1
        
        await self.report_status(
            status="reconnecting",
            discord_connection="disconnected"
        )
        
        if self.reconnect_attempts <= self.max_reconnect_attempts:
            delay = min(300, self.reconnect_delay * (2 ** (self.reconnect_attempts - 1)))
            logger.warning(f"Discord connection lost. Attempting reconnect {self.reconnect_attempts}/{self.max_reconnect_attempts} in {delay} seconds...")
            await asyncio.sleep(delay)
            try:
                await self.connect(reconnect=True)
            except Exception as e:
                logger.error(f"Reconnection attempt failed: {str(e)}", exc_info=True)
                await self.report_status(last_error=f"Reconnection failed: {str(e)}")
        else:
            logger.error("Max reconnection attempts reached. Please check Discord status and bot token.")
            await self.report_status(
                status="offline",
                discord_connection="failed",
                last_error="Max reconnection attempts reached"
            )

    async def report_status(self, **kwargs):
        """Report bot status to web dashboard"""
        try:
            if status_callback:
                status_callback(kwargs)
            
            # Also try to send to the web server
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'http://localhost:5000/log',
                    json={"type": "status", **kwargs},
                    timeout=2
                ) as resp:
                    pass
        except Exception as e:
            logger.debug(f"Failed to report status: {str(e)}")

class MusicCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_player(self, ctx):
        if ctx.guild.id not in self.bot.music_players:
            self.bot.music_players[ctx.guild.id] = MusicPlayer(self.bot, ctx)
        return self.bot.music_players[ctx.guild.id]

    @commands.command(name='join', help='Join your voice channel')
    async def join(self, ctx):
        """Join a voice channel"""
        try:
            self._increment_command_usage('join')
            
            if not ctx.author.voice:
                return await ctx.send("❌ You need to be in a voice channel!")

            if ctx.voice_client:
                if ctx.voice_client.channel == ctx.author.voice.channel:
                    return await ctx.send("✅ I'm already in your voice channel!")
                await ctx.voice_client.move_to(ctx.author.voice.channel)
                return await ctx.send(f"✅ Moved to {ctx.author.voice.channel.name}!")

            permissions = ctx.author.voice.channel.permissions_for(ctx.guild.me)
            if not permissions.connect or not permissions.speak:
                return await ctx.send("❌ I don't have permission to join or speak in your voice channel!")

            try:
                await ctx.author.voice.channel.connect(timeout=60.0, reconnect=True)
                logger.info(f"Joined voice channel in guild: {ctx.guild.id}")
                await ctx.send(f"✅ Joined {ctx.author.voice.channel.name}!")
                
                # Update voice connections count
                await self.bot.report_status(voice_connections=len(self.bot.voice_clients))
            except asyncio.TimeoutError:
                logger.error("Voice connection timed out")
                await ctx.send("❌ Failed to join voice channel due to timeout. Please try again.")
            except Exception as e:
                logger.error(f"Failed to join voice channel: {str(e)}")
                await ctx.send("❌ Failed to join voice channel. Please try again in a few moments.")
        except Exception as e:
            logger.error(f"Error joining voice channel: {str(e)}", exc_info=True)
            await ctx.send("❌ Could not join voice channel. Please try again.")

    @commands.command(name='play', help='Play a song from YouTube')
    async def play(self, ctx, *, query):
        """Play a song with given query or URL"""
        try:
            self._increment_command_usage('play')
            
            if not ctx.author.voice:
                return await ctx.send("❌ You need to be in a voice channel!")

            if not ctx.voice_client:
                await ctx.invoke(self.join)

            if not ctx.voice_client:
                return await ctx.send("❌ Could not connect to your voice channel.")

            player = self.get_player(ctx)
            async with ctx.typing():
                try:
                    search_type = "URL" if player.is_url(query) else "search"
                    await ctx.send(f"🔍 {search_type}ing for: `{query}`")
                    song_info = await player.add_to_queue(query)
                    
                    # Increment play count
                    stats["play_count"] += 1
                    await self.bot.report_status(play_count=stats["play_count"])
                    
                    await ctx.send(f"✅ Added to queue: **{song_info['title']}** ({format_duration(song_info['duration'])})")
                except Exception as e:
                    logger.error(f"Error adding song to queue: {str(e)}", exc_info=True)
                    await ctx.send(f"❌ Could not add song: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in play command: {str(e)}", exc_info=True)
            await ctx.send("❌ An unexpected error occurred. Please try again later.")

    @commands.command(name='stop', help='Stop playing and clear the queue')
    async def stop(self, ctx):
        """Stop the current song and clear the queue"""
        try:
            self._increment_command_usage('stop')
            
            if not ctx.voice_client:
                return await ctx.send("❌ I'm not playing anything!")

            player = self.get_player(ctx)
            await player.stop()
            await ctx.send("⏹️ Stopped playing and cleared the queue")
        except Exception as e:
            logger.error(f"Error stopping playback: {str(e)}", exc_info=True)
            await ctx.send("❌ Failed to stop playback. Please try again.")

    @commands.command(name='skip', help='Skip the current song')
    async def skip(self, ctx):
        """Skip the current song"""
        try:
            self._increment_command_usage('skip')
            
            if not ctx.voice_client or not ctx.voice_client.is_playing():
                return await ctx.send("❌ Nothing to skip!")

            player = self.get_player(ctx)
            await player.skip()
            await ctx.send("⏭️ Skipped current song")
        except Exception as e:
            logger.error(f"Error skipping song: {str(e)}", exc_info=True)
            await ctx.send("❌ Failed to skip the current song. Please try again.")

    @commands.command(name='queue', help='Display the current queue')
    async def queue(self, ctx):
        """Display the current queue"""
        try:
            self._increment_command_usage('queue')
            
            player = self.get_player(ctx)
            if not player.queue and not player.current:
                return await ctx.send("📪 Queue is empty")

            embed = discord.Embed(title="🎵 Music Queue", color=discord.Color.blue())

            if player.current:
                embed.add_field(
                    name="Now Playing",
                    value=f"**{player.current['title']}** ({format_duration(player.current['duration'])})",
                    inline=False
                )

            if player.queue:
                queue_list = "\n".join(
                    f"`{i+1}.` **{song['title']}** ({format_duration(song['duration'])})"
                    for i, song in enumerate(player.queue[:10])
                )
                remaining = len(player.queue) - 10 if len(player.queue) > 10 else 0
                queue_list += f"\n\n*And {remaining} more songs...*" if remaining else ""
                embed.add_field(name="Up Next", value=queue_list, inline=False)

            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"Error displaying queue: {str(e)}", exc_info=True)
            await ctx.send("❌ Failed to display the queue. Please try again.")

    @commands.command(name='volume', help='Set the volume (0-100)')
    async def volume(self, ctx, volume: int):
        """Set the volume of the player"""
        try:
            self._increment_command_usage('volume')
            
            if not ctx.voice_client:
                return await ctx.send("❌ I'm not currently playing!")

            if not 0 <= volume <= 100:
                return await ctx.send("❌ Volume must be between 0 and 100!")

            player = self.get_player(ctx)
            player.set_volume(volume / 100)
            await ctx.send(f"🔊 Volume set to {volume}%")
        except Exception as e:
            logger.error(f"Error setting volume: {str(e)}", exc_info=True)
            await ctx.send("❌ Failed to set volume. Please try again.")

    @commands.command(name='nowplaying', aliases=['np'], help='Show current song')
    async def nowplaying(self, ctx):
        """Display information about the current song"""
        try:
            self._increment_command_usage('nowplaying')
            
            player = self.get_player(ctx)
            if not player.current:
                return await ctx.send("❌ Nothing is playing right now!")

            track_info = await get_track_info(player.current)
            embed = discord.Embed(
                title="🎵 Now Playing",
                description=f"**{track_info['title']}**",
                color=discord.Color.blue()
            )
            
            embed.add_field(name="Duration", value=track_info['duration'], inline=True)
            embed.add_field(name="Requested by", value=track_info['requester'], inline=True)
            
            if track_info.get('webpage_url'):
                embed.add_field(name="Source", value=f"[Link]({track_info['webpage_url']})", inline=True)
                
            if track_info.get('thumbnail'):
                embed.set_thumbnail(url=track_info['thumbnail'])
                
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"Error displaying current song: {str(e)}", exc_info=True)
            await ctx.send("❌ Failed to get current song information.")

    @commands.command(name='leave', help='Leave the voice channel')
    async def leave(self, ctx):
        """Leave the voice channel"""
        try:
            self._increment_command_usage('leave')
            
            if not ctx.voice_client:
                return await ctx.send("❌ I'm not in a voice channel!")

            if ctx.guild.id in self.bot.music_players:
                player = self.bot.music_players[ctx.guild.id]
                await player.cleanup()
                self.bot.music_players.pop(ctx.guild.id, None)

            await ctx.voice_client.disconnect()
            await ctx.send("👋 Left the voice channel!")
            
            # Update voice connections count
            await self.bot.report_status(voice_connections=len(self.bot.voice_clients))
        except Exception as e:
            logger.error(f"Error leaving voice channel: {str(e)}", exc_info=True)
            await ctx.send("❌ Failed to leave the voice channel. Please try again.")
    
    @commands.command(name='help', help='Show available commands')
    async def help_command(self, ctx):
        """Show custom help message"""
        self._increment_command_usage('help')
        
        embed = discord.Embed(
            title="Radio FM Bot Commands",
            description="Here are the available commands:",
            color=discord.Color.blue()
        )
        
        commands_list = [
            ("!join", "Join your current voice channel"),
            ("!play <song name or URL>", "Play a song by name or URL"),
            ("!skip", "Skip the current song"),
            ("!queue", "Show the current song queue"),
            ("!stop", "Stop playback and clear the queue"),
            ("!leave", "Leave the voice channel"),
            ("!volume <1-100>", "Adjust the volume"),
            ("!nowplaying", "Show the currently playing song")
        ]
        
        for cmd, desc in commands_list:
            embed.add_field(name=cmd, value=desc, inline=False)
            
        embed.set_footer(text="Radio FM Bot | Developed with ❤️")
        await ctx.send(embed=embed)

    def _increment_command_usage(self, command_name):
        """Track command usage statistics"""
        if command_name not in stats["commands_used"]:
            stats["commands_used"][command_name] = 0
        stats["commands_used"][command_name] += 1

# Functions to interact with the bot outside this module
def get_uptime():
    """Get bot uptime as a string"""
    uptime_seconds = int(time.time() - start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def get_voice_connections():
    """Get number of active voice connections"""
    global bot
    if bot and hasattr(bot, 'voice_clients'):
        return len(bot.voice_clients)
    return 0

def set_status_callback(callback):
    """Set callback function for status updates"""
    global status_callback
    status_callback = callback

# Global bot instance
bot = None

def run_bot():
    """Initialize and run the bot"""
    global bot, bot_online, start_time
    
    try:
        token = os.environ.get('DISCORD_TOKEN')
        if not token:
            logger.error("No Discord token found in environment variables")
            return
        
        # Print token length and first/last characters for debugging
        token_len = len(token) if token else 0
        token_preview = f"{token[:4]}...{token[-4:]}" if token_len > 8 else "Invalid"
        logger.info(f"Token length: {token_len}, Preview: {token_preview}")
        
        start_time = time.time()
        logger.info("Creating bot instance...")
        
        # Create bot with sync_connection set to False to avoid blocking the thread
        # This allows better integration with Flask's event loop
        bot = RadioFMBot()
        logger.info("Bot instance created successfully")
        
        # This approach works better with our Flask integration
        async def start_bot():
            try:
                await bot.login(token)
                logger.info("Login successful!")
                
                # Start the connection
                logger.info("Starting bot connection...")
                await bot.connect(reconnect=True)
            except Exception as e:
                logger.error(f"Error in start_bot: {str(e)}", exc_info=True)
                
        # Run the bot with reconnect enabled in a separate thread
        logger.info("Starting bot connection...")
        future = asyncio.run_coroutine_threadsafe(start_bot(), bot.loop)
        
        # To check for errors, but not block
        def check_future(fut):
            try:
                fut.result()
            except Exception as e:
                logger.error(f"Bot connection error: {str(e)}", exc_info=True)
                
        future.add_done_callback(check_future)
        logger.info("Bot started in background")
        
    except discord.LoginFailure as e:
        logger.error(f"Invalid Discord token: {str(e)}. Please check your DISCORD_TOKEN environment variable.")
        bot_online = False
    except Exception as e:
        logger.error(f"Error running bot: {str(e)}", exc_info=True)
        bot_online = False
        # Try to gather additional diagnostic information
        try:
            import platform
            import sys
            logger.error(f"Python version: {sys.version}")
            logger.error(f"Platform: {platform.platform()}")
            logger.error(f"Discord.py version: {discord.__version__}")
        except Exception as diag_err:
            logger.error(f"Error getting diagnostic info: {str(diag_err)}")
