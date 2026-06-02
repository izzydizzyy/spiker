import discord
from discord.ext import commands
import logging
from utils.database import increment_message
from cogs.leaderboard import broadcast_leaderboard

log = logging.getLogger("events")

class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._msg_buffer = 0

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        await increment_message(message.author.id, message.author.display_name)
        # Broadcast to web every 10 messages to avoid spam
        self._msg_buffer += 1
        if self._msg_buffer >= 10:
            self._msg_buffer = 0
            await broadcast_leaderboard()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        log.info(f"Member joined: {member} ({member.id})")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        log.info(f"Member left: {member} ({member.id})")

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        log.info(f"CMD /{command.name} used by {interaction.user} ({interaction.user.id})")

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error):
        msg = "An error occurred. Please try again."
        if isinstance(error, discord.app_commands.errors.CheckFailure):
            msg = "❌ You don't have permission for that."
        elif isinstance(error, discord.app_commands.errors.CommandOnCooldown):
            msg = f"⏳ Slow down! Try again in `{error.retry_after:.1f}s`."
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)
        log.error(f"Command error in /{interaction.command}: {error}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))