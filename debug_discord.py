import discord
import os
import logging
import asyncio
import sys

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('debug_discord')

# Create a simple client
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    logger.info(f'Bot logged in as {client.user.name} (ID: {client.user.id})')
    logger.info(f'Connected to {len(client.guilds)} guilds')
    for guild in client.guilds:
        logger.info(f'- {guild.name} (ID: {guild.id})')
    
    # Exit after successful login
    await client.close()

@client.event
async def on_disconnect():
    logger.warning('Bot disconnected from Discord')

async def main():
    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        logger.error("No Discord token found in environment variables")
        return
    
    token_len = len(token) if token else 0
    token_preview = f"{token[:4]}...{token[-4:]}" if token_len > 8 else "Invalid"
    logger.info(f"Token length: {token_len}, Preview: {token_preview}")
    
    try:
        # Try to log in to Discord
        logger.info("Attempting to connect to Discord...")
        await client.login(token)
        logger.info("Login successful, connecting to gateway...")
        await client.connect()
    except discord.LoginFailure as e:
        logger.error(f"Invalid Discord token: {str(e)}")
    except discord.HTTPException as e:
        logger.error(f"HTTP Exception: {e.status} {e.text}")
    except Exception as e:
        logger.error(f"Error running bot: {str(e)}", exc_info=True)
    finally:
        logger.info("Test completed")

if __name__ == "__main__":
    asyncio.run(main())