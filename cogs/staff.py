import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
import logging
from utils.checks import is_staff
from utils.database import add_warning, get_warnings

log = logging.getLogger("staff")

class Staff(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /warn ──────────────────────────────────────────────────────────────────
    @app_commands.command(name="warn", description="Warn a user")
    @app_commands.describe(user="User to warn", reason="Reason for warning")
    @is_staff()
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        await add_warning(user.id, interaction.user.id, reason)
        warnings = await get_warnings(user.id)
        embed = discord.Embed(title="⚠️ User Warned", color=0xFFCC00)
        embed.add_field(name="User", value=user.mention, inline=True)
        embed.add_field(name="Mod", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text=f"Total warnings: {len(warnings)}")
        await interaction.response.send_message(embed=embed)
        try:
            await user.send(f"⚠️ You have been warned in **{interaction.guild.name}**.\n**Reason:** {reason}")
        except discord.Forbidden:
            pass

    # ── /warnings ─────────────────────────────────────────────────────────────
    @app_commands.command(name="warnings", description="View a user's warnings")
    @app_commands.describe(user="User to check")
    @is_staff()
    async def warnings_cmd(self, interaction: discord.Interaction, user: discord.Member):
        rows = await get_warnings(user.id)
        if not rows:
            return await interaction.response.send_message(f"{user.display_name} has no warnings.", ephemeral=True)
        lines = [f"`#{i+1}` — {r['reason']} *(by <@{r['mod_id']}> on {r['created_at'][:10]})*" for i, r in enumerate(rows)]
        embed = discord.Embed(
            title=f"Warnings for {user.display_name}",
            description="\n".join(lines),
            color=0xFFCC00
        )
        await interaction.response.send_message(embed=embed)

    # ── /timeout ──────────────────────────────────────────────────────────────
    @app_commands.command(name="timeout", description="Timeout a user")
    @app_commands.describe(user="User", minutes="Duration in minutes", reason="Reason")
    @is_staff()
    async def timeout_cmd(self, interaction: discord.Interaction, user: discord.Member, minutes: int, reason: str = "No reason provided"):
        until = discord.utils.utcnow() + timedelta(minutes=minutes)
        await user.timeout(until, reason=reason)
        embed = discord.Embed(title="🔇 User Timed Out", color=0xFF8C00)
        embed.add_field(name="User", value=user.mention, inline=True)
        embed.add_field(name="Duration", value=f"{minutes}m", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await interaction.response.send_message(embed=embed)

    # ── /kick ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="kick", description="Kick a member")
    @app_commands.describe(user="User", reason="Reason")
    @is_staff()
    async def kick_cmd(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
        await user.kick(reason=reason)
        embed = discord.Embed(title="👢 User Kicked", color=0xFF6B6B)
        embed.add_field(name="User", value=str(user), inline=True)
        embed.add_field(name="Mod", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await interaction.response.send_message(embed=embed)

    # ── /ban ──────────────────────────────────────────────────────────────────
    @app_commands.command(name="ban", description="Ban a member")
    @app_commands.describe(user="User", reason="Reason", delete_days="Days of messages to delete")
    @is_staff()
    async def ban_cmd(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided", delete_days: int = 0):
        await user.ban(reason=reason, delete_message_days=min(delete_days, 7))
        embed = discord.Embed(title="🔨 User Banned", color=0xFF0000)
        embed.add_field(name="User", value=str(user), inline=True)
        embed.add_field(name="Mod", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await interaction.response.send_message(embed=embed)

    # ── /unban ────────────────────────────────────────────────────────────────
    @app_commands.command(name="unban", description="Unban a user by ID")
    @app_commands.describe(user_id="User ID", reason="Reason")
    @is_staff()
    async def unban_cmd(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason"):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user, reason=reason)
            await interaction.response.send_message(f"✅ Unbanned `{user}`.")
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    # ── /purge ────────────────────────────────────────────────────────────────
    @app_commands.command(name="purge", description="Bulk delete messages")
    @app_commands.describe(amount="Number of messages to delete (max 100)")
    @is_staff()
    async def purge_cmd(self, interaction: discord.Interaction, amount: int):
        amount = min(amount, 100)
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🗑️ Deleted `{len(deleted)}` messages.", ephemeral=True)

    # ── /announce ─────────────────────────────────────────────────────────────
    @app_commands.command(name="announce", description="Send an announcement embed")
    @app_commands.describe(title="Title", message="Message body", channel="Target channel")
    @is_staff()
    async def announce(self, interaction: discord.Interaction, title: str, message: str, channel: discord.TextChannel = None):
        target = channel or interaction.channel
        embed = discord.Embed(title=title, description=message, color=0x00BFFF, timestamp=datetime.utcnow())
        embed.set_footer(text=f"Announced by {interaction.user.display_name}")
        await target.send(embed=embed)
        await interaction.response.send_message(f"✅ Announced in {target.mention}.", ephemeral=True)

    # ── /say ──────────────────────────────────────────────────────────────────
    @app_commands.command(name="say", description="Send a plain message as the bot")
    @app_commands.describe(message="Message to send", channel="Target channel")
    @is_staff()
    async def say_cmd(self, interaction: discord.Interaction, message: str, channel: discord.TextChannel = None):
        target = channel or interaction.channel
        await target.send(message)
        await interaction.response.send_message("✅ Sent.", ephemeral=True)

    # ── /test ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="test", description="Check bot is responsive")
    @is_staff()
    async def test(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"✅ Bot is online. Latency: `{round(self.bot.latency * 1000)}ms`", ephemeral=True)

    # ── /test-embed ───────────────────────────────────────────────────────────
    @app_commands.command(name="test-embed", description="Preview a test embed")
    @is_staff()
    async def test_embed(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Test Embed", description="This is a test embed.", color=0x00BFFF, timestamp=datetime.utcnow())
        embed.add_field(name="Field 1", value="Value 1", inline=True)
        embed.add_field(name="Field 2", value="Value 2", inline=True)
        embed.set_footer(text="Test embed footer")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Staff(bot))