import os
import discord
from discord.ext import commands
import logging
import sys
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('discord_bot')

# Discord bot class with better recovery
class RadioFMBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            reconnect=True
        )
        
        # Add music commands cog
        self.add_cog(MusicCommands(self))
        
        # Track connection attempts
        self.reconnect_attempts = 0
        self.max_reconnects = 10
        self.initial_backoff = 1
        self.connected = False
        
    async def setup_hook(self):
        """This is called when the bot is preparing to start"""
        logger.info("Setting up RadioFMBot...")
        
        # Start heartbeat task
        self.heartbeat_task = self.loop.create_task(self.heartbeat())
        
    async def heartbeat(self):
        """Send heartbeat to maintain connection"""
        await self.wait_until_ready()
        while not self.is_closed():
            logger.debug("Heartbeat sent")
            await asyncio.sleep(60)  # Every minute
            
    async def on_ready(self):
        """Called when the bot is ready and connected"""
        self.connected = True
        self.reconnect_attempts = 0  # Reset counter on successful connection
        
        logger.info(f'Bot is connected to Discord! Logged in as {self.user.name} (ID: {self.user.id})')
        logger.info(f'Connected to {len(self.guilds)} guilds:')
        for guild in self.guilds:
            logger.info(f'- {guild.name} (ID: {guild.id})')
        
        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="!help"
            )
        )
            
class MusicCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}  # Store music players for each guild
        
    def get_player(self, ctx):
        """Get or create a player for this guild"""
        # Import music_player here to avoid circular imports
        import music_player
        
        if ctx.guild.id not in self.players:
            self.players[ctx.guild.id] = music_player.MusicPlayer(self.bot, ctx)
        return self.players[ctx.guild.id]
        
    @commands.command(name='join')
    async def join(self, ctx):
        """Join a voice channel"""
        if ctx.author.voice is None:
            return await ctx.send("You must be in a voice channel to use this command.")
        
        voice_channel = ctx.author.voice.channel
        if ctx.voice_client is not None:
            await ctx.voice_client.move_to(voice_channel)
        else:
            await voice_channel.connect()
        
        await ctx.send(f"Connected to {voice_channel.name}")
        
    @commands.command(name='help')
    async def help_command(self, ctx):
        """Show custom help message"""
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

async def main():
    """Main function to run the bot"""
    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        logger.error('DISCORD_TOKEN not found in environment variables')
        return
    
    try:
        # Try to use uvloop for better performance if available
        try:
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            logger.info("Using uvloop for better performance")
        except ImportError:
            logger.info("uvloop not available, using standard event loop")
        
        # Create bot
        bot = RadioFMBot()
        
        # Run bot with reconnection
        async def runner():
            try:
                logger.info("Starting RadioFMBot...")
                await bot.start(token)
            except (discord.ConnectionClosed, discord.GatewayNotFound) as e:
                logger.error(f"Connection error: {e}")
            except Exception as e:
                logger.error(f"Unexpected error: {e}", exc_info=True)
        
        # Start the bot
        await runner()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}", exc_info=True)

# Run the bot
if __name__ == '__main__':
    if sys.platform == 'win32':
        # Windows-specific event loop policy
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())