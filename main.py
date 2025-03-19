from flask import Flask, render_template, jsonify, request
import threading
import os
import logging
import datetime
import time
import json
import sys

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('main')

# Global variables for bot status tracking
bot_status = {
    "status": "starting",
    "started_at": time.time(),
    "discord_connection": "disconnecting",
    "voice_connections": 0,
    "errors": [],
    "last_error": None,
    "play_count": 0,
    "ffmpeg_status": "checking"
}

# Create Flask app
app = Flask(__name__)

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    """Full dashboard with more details"""
    return render_template('dashboard.html')

@app.route('/bot-status')
def get_bot_status():
    """API endpoint to get bot status"""
    global bot_status
    
    # Calculate uptime
    uptime_seconds = int(time.time() - bot_status["started_at"])
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    response = {
        "status": bot_status["status"],
        "uptime": uptime,
        "uptime_seconds": uptime_seconds,
        "discord_connection": bot_status["discord_connection"],
        "voice_connections": bot_status["voice_connections"],
        "last_error": bot_status["last_error"],
        "play_count": bot_status["play_count"],
        "ffmpeg_status": bot_status["ffmpeg_status"],
        "timestamp": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    return jsonify(response)

@app.route('/log', methods=['POST'])
def log_event():
    """Endpoint for the bot to log events"""
    try:
        data = request.json
        event_type = data.get('type', 'info')
        message = data.get('message', '')
        
        if event_type == 'error':
            bot_status["errors"].append({
                "time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "message": message
            })
            bot_status["last_error"] = message
            logger.error(f"Bot error: {message}")
        elif event_type == 'status':
            bot_status["status"] = data.get('status', bot_status["status"])
            bot_status["discord_connection"] = data.get('discord_connection', bot_status["discord_connection"])
            bot_status["voice_connections"] = data.get('voice_connections', bot_status["voice_connections"])
            bot_status["ffmpeg_status"] = data.get('ffmpeg_status', bot_status["ffmpeg_status"])
            
            if data.get('play_count'):
                bot_status["play_count"] = data.get('play_count')
                
            logger.info(f"Status update: {bot_status['status']}")
        else:
            logger.info(f"Bot log: {message}")
            
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error in log_event: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)})

@app.route('/health')
def health_check():
    """Simple health check endpoint"""
    return jsonify({
        "status": "healthy",
        "bot_status": bot_status["status"],
        "timestamp": datetime.datetime.now().isoformat()
    })

def check_ffmpeg():
    """Check if ffmpeg is available"""
    try:
        # Try to find ffmpeg in different locations
        ffmpeg_paths = [
            '/usr/bin/ffmpeg',
            '/usr/local/bin/ffmpeg',
            '/nix/store/*/ffmpeg-*/bin/ffmpeg',
            'ffmpeg'
        ]
        
        for path in ffmpeg_paths:
            if '*' in path:
                # Handle wildcards for nix store
                import glob
                matches = glob.glob(path)
                if matches:
                    path = matches[0]
            
            if os.path.exists(path) or os.system(f"which {path} > /dev/null 2>&1") == 0:
                logger.info(f"Found ffmpeg at: {path}")
                bot_status["ffmpeg_status"] = "available"
                return True
                
        logger.warning("FFmpeg not found in common paths")
        bot_status["ffmpeg_status"] = "not_found"
        return False
    except Exception as e:
        logger.error(f"Error checking for ffmpeg: {str(e)}", exc_info=True)
        bot_status["ffmpeg_status"] = "error"
        return False

def create_cookies_file():
    """Create cookies file from environment variable if available"""
    try:
        if 'COOKIES_BASE64' in os.environ and os.environ['COOKIES_BASE64']:
            import base64
            cookies_path = os.path.join(os.getcwd(), 'cookies.txt')
            
            with open(cookies_path, 'wb') as f:
                f.write(base64.b64decode(os.environ['COOKIES_BASE64']))
                
            logger.info(f"Created cookies file at {cookies_path}")
            
            # Verify the file exists and has content
            if os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 0:
                return True
            else:
                logger.error("Created cookies file but it's empty or not accessible")
                return False
    except Exception as e:
        logger.error(f"Error creating cookies file: {str(e)}", exc_info=True)
        return False

def run_discord_bot():
    """Function to run the Discord bot"""
    try:
        logger.info("Starting Discord bot...")
        
        # For Railway deployment, we'll skip the ffmpeg and cookies checks
        if 'RAILWAY_ENVIRONMENT' not in os.environ:
            # Only run these checks in non-Railway environments
            ffmpeg_available = check_ffmpeg()
            if not ffmpeg_available:
                logger.warning("FFmpeg not found. Audio playback may not work correctly.")
                
            cookies_created = create_cookies_file()
            if not cookies_created and 'COOKIES_BASE64' in os.environ:
                logger.warning("Failed to create cookies file from COOKIES_BASE64.")
        
        # First try the simplified approach - it's more reliable for Railway deployment
        try:
            import discord
            from discord.ext import commands
            import asyncio
            
            # Create intents
            intents = discord.Intents.default()
            intents.message_content = True
            intents.voice_states = True
            
            # Create bot instance
            bot = commands.Bot(command_prefix='!', intents=intents)
            
            # Status update coroutine
            async def update_bot_status():
                while True:
                    try:
                        # Update status in dashboard
                        status_data = {
                            "status": "online",
                            "discord_connection": "connected" if bot.is_ready() else "connecting",
                            "voice_connections": len(bot.voice_clients)
                        }
                        update_status(status_data)
                        await asyncio.sleep(30)  # Update every 30 seconds
                    except Exception as e:
                        logger.error(f"Error in status update: {str(e)}")
                        await asyncio.sleep(60)  # Longer wait on error
            
            @bot.event
            async def on_ready():
                logger.info(f'Bot is ready! Logged in as {bot.user.name} (ID: {bot.user.id})')
                logger.info(f'Connected to {len(bot.guilds)} guilds:')
                for guild in bot.guilds:
                    logger.info(f'- {guild.name} (ID: {guild.id})')
                    
                await bot.change_presence(activity=discord.Activity(
                    type=discord.ActivityType.listening,
                    name="!help for commands"
                ))
                
                # Start status updater
                bot.loop.create_task(update_bot_status())
                
                # Update status immediately
                update_status({
                    "status": "online",
                    "discord_connection": "connected",
                    "voice_connections": len(bot.voice_clients)
                })
            
            @bot.event
            async def on_disconnect():
                logger.warning("Bot disconnected from Discord")
                update_status({
                    "discord_connection": "disconnected"
                })
            
            @bot.command(name='ping')
            async def ping(ctx):
                """Simple command to test if the bot is responsive"""
                await ctx.send(f'Pong! Latency: {round(bot.latency * 1000)}ms')
            
            # Music commands
            @bot.command(name='join')
            async def join(ctx):
                """Join a voice channel"""
                if ctx.author.voice is None:
                    return await ctx.send("You must be in a voice channel to use this command.")
                
                voice_channel = ctx.author.voice.channel
                if ctx.voice_client is not None:
                    await ctx.voice_client.move_to(voice_channel)
                else:
                    await voice_channel.connect()
                
                await ctx.send(f"Connected to {voice_channel.name}")
            
            @bot.command(name='play')
            async def play(ctx, *, query):
                """Play a song with given query or URL"""
                # Make sure the bot is in a voice channel
                if ctx.voice_client is None:
                    if ctx.author.voice:
                        await ctx.author.voice.channel.connect()
                    else:
                        return await ctx.send("You must be in a voice channel to use this command.")
                
                import music_player
                
                # Get or create the music player for this server
                players = getattr(bot, 'music_players', {})
                if ctx.guild.id not in players:
                    players[ctx.guild.id] = music_player.MusicPlayer(bot, ctx)
                    bot.music_players = players
                
                player = players[ctx.guild.id]
                
                # Process the query and add to queue
                await ctx.send(f"Searching for: {query}")
                try:
                    song_info = await player.add_to_queue(query)
                    await ctx.send(f"Added to queue: **{song_info['title']}**")
                except Exception as e:
                    await ctx.send(f"Error: {str(e)}")
            
            @bot.command(name='stop')
            async def stop(ctx):
                """Stop the current song and clear the queue"""
                # Check if bot is in a voice channel
                if ctx.voice_client is None:
                    return await ctx.send("I'm not currently playing anything.")
                
                # Get the music player for this server
                players = getattr(bot, 'music_players', {})
                if ctx.guild.id in players:
                    player = players[ctx.guild.id]
                    await player.stop()
                
                # Stop and disconnect
                ctx.voice_client.stop()
                await ctx.voice_client.disconnect()
                await ctx.send("Stopped the music and cleared the queue.")
            
            @bot.command(name='skip')
            async def skip(ctx):
                """Skip the current song"""
                if ctx.voice_client is None:
                    return await ctx.send("I'm not currently playing anything.")
                
                # Get the music player for this server
                players = getattr(bot, 'music_players', {})
                if ctx.guild.id in players:
                    player = players[ctx.guild.id]
                    await player.skip()
                    await ctx.send("Skipped the current song.")
                else:
                    ctx.voice_client.stop()
                    await ctx.send("Skipped the current song.")
            
            @bot.command(name='queue')
            async def queue(ctx):
                """Display the current queue"""
                # Get the music player for this server
                players = getattr(bot, 'music_players', {})
                if ctx.guild.id not in players or not players[ctx.guild.id].queue:
                    return await ctx.send("The queue is empty.")
                
                player = players[ctx.guild.id]
                
                # Format the queue
                queue_list = []
                for i, song in enumerate(player.queue, 1):
                    queue_list.append(f"{i}. **{song['title']}**")
                
                if player.current:
                    now_playing = f"Now playing: **{player.current['title']}**\n\n"
                else:
                    now_playing = ""
                
                await ctx.send(f"{now_playing}Queue:\n" + "\n".join(queue_list[:10]) + 
                              (f"\n... and {len(player.queue) - 10} more" if len(player.queue) > 10 else ""))
            
            @bot.command(name='leave')
            async def leave(ctx):
                """Leave the voice channel"""
                if ctx.voice_client is not None:
                    # Get the music player for this server
                    players = getattr(bot, 'music_players', {})
                    if ctx.guild.id in players:
                        player = players[ctx.guild.id]
                        await player.cleanup()
                    
                    await ctx.voice_client.disconnect()
                    await ctx.send("Left the voice channel.")
                else:
                    await ctx.send("I'm not in a voice channel.")
            
            @bot.command(name='help')
            async def help_command(ctx):
                """Show help message"""
                help_text = """
                **Radio FM Bot Commands**
                
                **Music Commands:**
                `!join` - Join your voice channel
                `!play <song>` - Play a song (URL or search query)
                `!stop` - Stop playing and clear the queue
                `!skip` - Skip the current song
                `!queue` - Show the current queue
                `!leave` - Leave the voice channel
                
                **Other Commands:**
                `!ping` - Check bot latency
                `!help` - Show this help message
                """
                await ctx.send(help_text)
            
            # Get token and run bot
            token = os.environ.get('DISCORD_TOKEN')
            if not token:
                logger.error("No Discord token found in environment variables")
                return
                
            logger.info("Starting simplified bot...")
            bot.run(token, reconnect=True)
            
        except Exception as simple_bot_error:
            # If simplified approach fails, fall back to the original implementation
            logger.error(f"Error with simplified bot: {str(simple_bot_error)}. Trying original implementation...")
            
            # Import bot here to avoid circular imports
            import bot
            bot.set_status_callback(update_status)
            bot.run_bot()
            
    except Exception as e:
        logger.error(f"Error starting Discord bot: {str(e)}", exc_info=True)
        bot_status["status"] = "error"
        bot_status["last_error"] = str(e)

def update_status(status_data):
    """Callback to update bot status from the bot module"""
    global bot_status
    for key, value in status_data.items():
        if key in bot_status:
            bot_status[key] = value
    
    logger.debug(f"Updated status: {json.dumps(bot_status, default=str)}")

# Initialize the bot when the module is loaded, not just when run directly
# This ensures the bot starts when using Gunicorn
has_token = bool(os.environ.get('DISCORD_TOKEN'))
logger.info(f"Discord token present: {has_token}")

if not has_token:
    logger.error("DISCORD_TOKEN environment variable not set!")
    bot_status["status"] = "error"
    bot_status["last_error"] = "DISCORD_TOKEN not set"
else:
    # Start bot in a separate thread with better error handling
    try:
        discord_thread = threading.Thread(target=run_discord_bot, daemon=True)
        discord_thread.start()
        logger.info("Discord bot thread started")
    except Exception as e:
        logger.error(f"Failed to start Discord bot thread: {str(e)}", exc_info=True)
        bot_status["status"] = "error"
        bot_status["last_error"] = f"Failed to start bot: {str(e)}"

if __name__ == "__main__":
    # Run the Flask app directly when script is run
    app.run(host="0.0.0.0", port=5000, debug=True)
