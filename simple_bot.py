import os
import discord
from discord.ext import commands
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('discord_bot')

# Discord setup
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    """Called when the bot is ready and connected"""
    logger.info(f'Bot is connected to Discord! Logged in as {bot.user.name} (ID: {bot.user.id})')
    logger.info(f'Connected to {len(bot.guilds)} guilds:')
    for guild in bot.guilds:
        logger.info(f'- {guild.name} (ID: {guild.id})')
    
    # Set bot status to "Listening to !help"
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="!help"
        )
    )

@bot.command(name='ping')
async def ping(ctx):
    """Simple command to test if the bot is responsive"""
    await ctx.send(f'Pong! Bot latency: {round(bot.latency * 1000)}ms')

@bot.command(name='hello')
async def hello(ctx):
    """Simple greeting command"""
    await ctx.send(f'Hello {ctx.author.mention}! I am Radio FM, your music bot!')

def main():
    """Main function to run the bot"""
    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        logger.error('DISCORD_TOKEN not found in environment variables')
        return
    
    logger.info('Starting simplified bot...')
    bot.run(token)

if __name__ == '__main__':
    main()