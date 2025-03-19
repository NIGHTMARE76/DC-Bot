import os
import logging
import discord
from discord.ext import commands
import asyncio
import sys

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('discord_debug')

# Get token from environment
TOKEN = os.environ.get('DISCORD_TOKEN')
if not TOKEN:
    logger.error("No Discord token found in environment variables!")
    sys.exit(1)

# Print token details for verification (safely)
token_length = len(TOKEN)
token_preview = TOKEN[:3] + "..." + TOKEN[-4:] if token_length > 10 else "TOO_SHORT"
logger.info(f"Token length: {token_length}, Preview: {token_preview}")

# Create intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

# Create bot with detailed logging
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    logger.info(f"Bot is ready! Logged in as {bot.user.name} (ID: {bot.user.id})")
    logger.info(f"Connected to {len(bot.guilds)} guilds:")
    for guild in bot.guilds:
        logger.info(f"- {guild.name} (ID: {guild.id})")
    logger.info(f"Bot latency: {round(bot.latency * 1000)}ms")

@bot.event
async def on_connect():
    logger.info("Bot connected to Discord!")

@bot.event 
async def on_disconnect():
    logger.error("Bot disconnected from Discord!")

@bot.event
async def on_error(event, *args, **kwargs):
    logger.error(f"Error in event {event}: {sys.exc_info()}")

@bot.event
async def on_command_error(ctx, error):
    logger.error(f"Command error: {error}")

@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! Bot latency: {round(bot.latency * 1000)}ms")

logger.info("Starting bot with detailed logging...")
try:
    bot.run(TOKEN, log_handler=None)
except Exception as e:
    logger.critical(f"Failed to start bot: {e}")
    # Print more detailed error
    import traceback
    logger.critical(traceback.format_exc())