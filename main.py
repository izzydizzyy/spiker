import discord
from discord.ext import commands, tasks
import asyncio
import os
import logging
from datetime import datetime, time
import pytz

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("bot")

TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_TOKEN_HERE")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))  # Your server ID

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        from utils.database import init_db
        await init_db()

        cogs = ["cogs.leaderboard", "cogs.squads", "cogs.reports", "cogs.staff", "cogs.events"]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                log.info(f"Loaded {cog}")
            except Exception as e:
                log.error(f"Failed to load {cog}: {e}")

        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        log.info("Commands synced")

    async def on_ready(self):
        log.info(f"Logged in as {self.user} ({self.user.id})")
        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching, name="the leaderboard 👀"
        ))

bot = Bot()

if __name__ == "__main__":
    bot.run(TOKEN)