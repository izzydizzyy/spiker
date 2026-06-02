import discord
from discord.ext import commands
from discord import app_commands
import logging

log = logging.getLogger("vc")

# ID of the "Join to Create" voice channel
JOIN_TO_CREATE_ID = 1492386307534753802

# Tracks active courts: {channel_id: owner_id}
active_courts: dict[int, int] = {}


class VC(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Auto-create/delete courts ──────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild

        # User joined the "Join to Create" channel
        if after.channel and after.channel.id == JOIN_TO_CREATE_ID:
            category = after.channel.category
            court = await guild.create_voice_channel(
                name=f"🏐 {member.display_name}'s Court",
                category=category,
                reason="Temp court created"
            )
            active_courts[court.id] = member.id
            await member.move_to(court)
            log.info(f"Created court for {member} → #{court.name}")

        # User left a court — delete if empty
        if before.channel and before.channel.id in active_courts:
            if len(before.channel.members) == 0:
                del active_courts[before.channel.id]
                await before.channel.delete(reason="Court empty")
                log.info(f"Deleted empty court #{before.channel.name}")

    # ── Helper: get user's court ───────────────────────────────────────────────
    def get_court(self, member: discord.Member) -> discord.VoiceChannel | None:
        if not member.voice or not member.voice.channel:
            return None
        ch = member.voice.channel
        if ch.id in active_courts and active_courts[ch.id] == member.id:
            return ch
        return None

    def in_court(self, member: discord.Member) -> discord.VoiceChannel | None:
        """Returns the court the member is in, even if not owner."""
        if not member.voice or not member.voice.channel:
            return None
        ch = member.voice.channel
        if ch.id in active_courts:
            return ch
        return None

    # ── /lock-court ────────────────────────────────────────────────────────────
    @app_commands.command(name="lock-court", description="Lock your court so no one else can join")
    async def lock_court(self, interaction: discord.Interaction):
        court = self.get_court(interaction.user)
        if not court:
            return await interaction.response.send_message("❌ You don't own a court.", ephemeral=True)
        await court.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message("🔒 Court locked!", ephemeral=True)

    # ── /unlock-court ──────────────────────────────────────────────────────────
    @app_commands.command(name="unlock-court", description="Unlock your court for everyone")
    async def unlock_court(self, interaction: discord.Interaction):
        court = self.get_court(interaction.user)
        if not court:
            return await interaction.response.send_message("❌ You don't own a court.", ephemeral=True)
        await court.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message("🔓 Court unlocked!", ephemeral=True)

    # ── /rename-court ──────────────────────────────────────────────────────────
    @app_commands.command(name="rename-court", description="Rename your court")
    @app_commands.describe(name="New name for your court")
    async def rename_court(self, interaction: discord.Interaction, name: str):
        court = self.get_court(interaction.user)
        if not court:
            return await interaction.response.send_message("❌ You don't own a court.", ephemeral=True)
        await court.edit(name=f"🏐 {name}")
        await interaction.response.send_message(f"✅ Court renamed to **🏐 {name}**!", ephemeral=True)

    # ── /limit-court ───────────────────────────────────────────────────────────
    @app_commands.command(name="limit-court", description="Set a player limit for your court")
    @app_commands.describe(limit="Max number of players (0 = unlimited)")
    async def limit_court(self, interaction: discord.Interaction, limit: int):
        court = self.get_court(interaction.user)
        if not court:
            return await interaction.response.send_message("❌ You don't own a court.", ephemeral=True)
        if limit < 0 or limit > 99:
            return await interaction.response.send_message("❌ Limit must be between 0 and 99.", ephemeral=True)
        await court.edit(user_limit=limit)
        msg = f"✅ Player limit set to **{limit}**!" if limit > 0 else "✅ Player limit removed!"
        await interaction.response.send_message(msg, ephemeral=True)

    # ── /invite-court ──────────────────────────────────────────────────────────
    @app_commands.command(name="invite-court", description="Allow a specific user into your locked court")
    @app_commands.describe(user="User to invite")
    async def invite_court(self, interaction: discord.Interaction, user: discord.Member):
        court = self.get_court(interaction.user)
        if not court:
            return await interaction.response.send_message("❌ You don't own a court.", ephemeral=True)
        await court.set_permissions(user, connect=True)
        await interaction.response.send_message(f"✅ **{user.display_name}** has been invited to your court!", ephemeral=True)

    # ── /kick-court ────────────────────────────────────────────────────────────
    @app_commands.command(name="kick-court", description="Kick a player from your court")
    @app_commands.describe(user="User to kick from your court")
    async def kick_court(self, interaction: discord.Interaction, user: discord.Member):
        court = self.get_court(interaction.user)
        if not court:
            return await interaction.response.send_message("❌ You don't own a court.", ephemeral=True)
        if user == interaction.user:
            return await interaction.response.send_message("❌ You can't kick yourself.", ephemeral=True)
        if user.voice and user.voice.channel == court:
            await user.move_to(None)
            await court.set_permissions(user, connect=False)
            await interaction.response.send_message(f"👢 **{user.display_name}** was kicked from your court!", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ **{user.display_name}** is not in your court.", ephemeral=True)

    # ── /transfer-court ────────────────────────────────────────────────────────
    @app_commands.command(name="transfer-court", description="Transfer ownership of your court to another player")
    @app_commands.describe(user="User to transfer ownership to")
    async def transfer_court(self, interaction: discord.Interaction, user: discord.Member):
        court = self.get_court(interaction.user)
        if not court:
            return await interaction.response.send_message("❌ You don't own a court.", ephemeral=True)
        if user == interaction.user:
            return await interaction.response.send_message("❌ You already own this court.", ephemeral=True)
        if not (user.voice and user.voice.channel == court):
            return await interaction.response.send_message(f"❌ **{user.display_name}** must be in your court.", ephemeral=True)
        active_courts[court.id] = user.id
        await court.edit(name=f"🏐 {user.display_name}'s Court")
        await interaction.response.send_message(f"✅ Court transferred to **{user.display_name}**!", ephemeral=True)

    # ── /court-info ────────────────────────────────────────────────────────────
    @app_commands.command(name="court-info", description="View info about your current court")
    async def court_info(self, interaction: discord.Interaction):
        court = self.in_court(interaction.user)
        if not court:
            return await interaction.response.send_message("❌ You're not in a court.", ephemeral=True)

        owner_id = active_courts.get(court.id)
        owner = interaction.guild.get_member(owner_id)
        players = [m.display_name for m in court.members]
        limit = court.user_limit if court.user_limit > 0 else "Unlimited"
        locked = court.overwrites_for(interaction.guild.default_role).connect is False

        embed = discord.Embed(title=court.name, color=0x00BFFF)
        embed.add_field(name="Owner", value=owner.display_name if owner else "Unknown", inline=True)
        embed.add_field(name="Players", value=f"{len(players)}/{limit}", inline=True)
        embed.add_field(name="Status", value="🔒 Locked" if locked else "🔓 Open", inline=True)
        embed.add_field(name="In Court", value=", ".join(players) or "Empty", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(VC(bot))