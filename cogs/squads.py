import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import logging
from utils.database import (
    create_squad, get_squad_by_name, get_user_squad, get_squad_members,
    update_squad_member_role, add_squad_member, remove_squad_member,
    delete_squad, rename_squad, get_squad_leaderboard
)

log = logging.getLogger("squads")

ROLE_ICONS = {"owner": "👑", "co-owner": "⚔️", "member": "🛡️"}

class Squads(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    squad = app_commands.Group(name="squad", description="Squad management commands")

    # ── /squad create ──────────────────────────────────────────────────────────
    @squad.command(name="create", description="Create a new squad")
    @app_commands.describe(name="Squad name (max 32 chars)")
    @app_commands.checks.cooldown(1, 30)
    async def squad_create(self, interaction: discord.Interaction, name: str):
        if len(name) > 32:
            return await interaction.response.send_message("Squad name must be 32 characters or less.", ephemeral=True)

        existing = await get_user_squad(interaction.user.id)
        if existing:
            return await interaction.response.send_message("You're already in a squad. Leave it first.", ephemeral=True)

        squad_id = await create_squad(name, interaction.user.id)
        if not squad_id:
            return await interaction.response.send_message(f"A squad named **{name}** already exists.", ephemeral=True)

        embed = discord.Embed(title="✅ Squad Created!", color=0x00BFFF)
        embed.add_field(name="Name", value=name, inline=True)
        embed.add_field(name="Owner", value=interaction.user.mention, inline=True)
        embed.set_footer(text=f"Squad ID: {squad_id}")
        await interaction.response.send_message(embed=embed)

    # ── /squad delete ──────────────────────────────────────────────────────────
    @squad.command(name="delete", description="Delete your squad (owner only)")
    async def squad_delete(self, interaction: discord.Interaction):
        row = await get_user_squad(interaction.user.id)
        if not row or row["role"] != "owner":
            return await interaction.response.send_message("You must be the squad owner to delete it.", ephemeral=True)

        view = ConfirmView(interaction.user)
        await interaction.response.send_message(
            f"⚠️ Are you sure you want to delete **{row['name']}**? This cannot be undone.",
            view=view, ephemeral=True
        )
        await view.wait()
        if view.confirmed:
            await delete_squad(row["id"])
            await interaction.edit_original_response(content="✅ Squad deleted.", view=None)
        else:
            await interaction.edit_original_response(content="Cancelled.", view=None)

    # ── /squad rename ──────────────────────────────────────────────────────────
    @squad.command(name="rename", description="Rename your squad")
    @app_commands.describe(new_name="New squad name")
    async def squad_rename(self, interaction: discord.Interaction, new_name: str):
        if len(new_name) > 32:
            return await interaction.response.send_message("Name must be 32 chars or less.", ephemeral=True)
        row = await get_user_squad(interaction.user.id)
        if not row or row["role"] not in ("owner", "co-owner"):
            return await interaction.response.send_message("You need to be an owner or co-owner.", ephemeral=True)
        success = await rename_squad(row["id"], new_name)
        if not success:
            return await interaction.response.send_message("That name is already taken.", ephemeral=True)
        await interaction.response.send_message(f"✅ Squad renamed to **{new_name}**.")

    # ── /squad invite ──────────────────────────────────────────────────────────
    @squad.command(name="invite", description="Invite a user to your squad")
    @app_commands.describe(user="User to invite")
    async def squad_invite(self, interaction: discord.Interaction, user: discord.Member):
        if user.bot:
            return await interaction.response.send_message("Can't invite bots.", ephemeral=True)
        row = await get_user_squad(interaction.user.id)
        if not row or row["role"] not in ("owner", "co-owner"):
            return await interaction.response.send_message("You need to be an owner or co-owner to invite.", ephemeral=True)
        target_squad = await get_user_squad(user.id)
        if target_squad:
            return await interaction.response.send_message(f"{user.display_name} is already in a squad.", ephemeral=True)

        view = InviteView(user, row["id"], row["name"])
        await interaction.response.send_message(
            f"📨 Invite sent to {user.mention} for squad **{row['name']}**.", ephemeral=True
        )
        try:
            await user.send(
                f"You've been invited to join **{row['name']}** by {interaction.user.mention}!",
                view=view
            )
        except discord.Forbidden:
            msg = await interaction.channel.send(
                f"{user.mention}, you've been invited to join **{row['name']}**!",
                view=view
            )

    # ── /squad kick ───────────────────────────────────────────────────────────
    @squad.command(name="kick", description="Kick a member from your squad")
    @app_commands.describe(user="User to kick")
    async def squad_kick(self, interaction: discord.Interaction, user: discord.Member):
        row = await get_user_squad(interaction.user.id)
        if not row or row["role"] not in ("owner", "co-owner"):
            return await interaction.response.send_message("You need to be an owner or co-owner.", ephemeral=True)
        target = await get_user_squad(user.id)
        if not target or target["id"] != row["id"]:
            return await interaction.response.send_message(f"{user.display_name} is not in your squad.", ephemeral=True)
        if target["role"] == "owner":
            return await interaction.response.send_message("You can't kick the owner.", ephemeral=True)
        await remove_squad_member(row["id"], user.id)
        await interaction.response.send_message(f"✅ Kicked {user.mention} from the squad.")

    # ── /squad promote ────────────────────────────────────────────────────────
    @squad.command(name="promote", description="Promote a member to Co-Owner")
    @app_commands.describe(user="Member to promote")
    async def squad_promote(self, interaction: discord.Interaction, user: discord.Member):
        row = await get_user_squad(interaction.user.id)
        if not row or row["role"] != "owner":
            return await interaction.response.send_message("Only the owner can promote.", ephemeral=True)
        target = await get_user_squad(user.id)
        if not target or target["id"] != row["id"]:
            return await interaction.response.send_message(f"{user.display_name} is not in your squad.", ephemeral=True)
        await update_squad_member_role(row["id"], user.id, "co-owner")
        await interaction.response.send_message(f"⚔️ {user.mention} has been promoted to **Co-Owner**!")

    # ── /squad demote ─────────────────────────────────────────────────────────
    @squad.command(name="demote", description="Demote a Co-Owner to Member")
    @app_commands.describe(user="Co-Owner to demote")
    async def squad_demote(self, interaction: discord.Interaction, user: discord.Member):
        row = await get_user_squad(interaction.user.id)
        if not row or row["role"] != "owner":
            return await interaction.response.send_message("Only the owner can demote.", ephemeral=True)
        target = await get_user_squad(user.id)
        if not target or target["id"] != row["id"] or target["role"] != "co-owner":
            return await interaction.response.send_message(f"{user.display_name} is not a Co-Owner in your squad.", ephemeral=True)
        await update_squad_member_role(row["id"], user.id, "member")
        await interaction.response.send_message(f"🛡️ {user.mention} has been demoted to **Member**.")

    # ── /squad transfer ───────────────────────────────────────────────────────
    @squad.command(name="transfer", description="Transfer ownership to another member")
    @app_commands.describe(user="New owner")
    async def squad_transfer(self, interaction: discord.Interaction, user: discord.Member):
        row = await get_user_squad(interaction.user.id)
        if not row or row["role"] != "owner":
            return await interaction.response.send_message("Only the owner can transfer.", ephemeral=True)
        target = await get_user_squad(user.id)
        if not target or target["id"] != row["id"]:
            return await interaction.response.send_message(f"{user.display_name} is not in your squad.", ephemeral=True)
        await update_squad_member_role(row["id"], interaction.user.id, "member")
        await update_squad_member_role(row["id"], user.id, "owner")
        await interaction.response.send_message(f"👑 Ownership transferred to {user.mention}!")

    # ── /squad leave ──────────────────────────────────────────────────────────
    @squad.command(name="leave", description="Leave your current squad")
    async def squad_leave(self, interaction: discord.Interaction):
        row = await get_user_squad(interaction.user.id)
        if not row:
            return await interaction.response.send_message("You're not in a squad.", ephemeral=True)
        if row["role"] == "owner":
            return await interaction.response.send_message("Transfer ownership or delete the squad before leaving.", ephemeral=True)
        await remove_squad_member(row["id"], interaction.user.id)
        await interaction.response.send_message(f"✅ You left **{row['name']}**.")

    # ── /squad info ───────────────────────────────────────────────────────────
    @squad.command(name="info", description="View squad info")
    @app_commands.describe(name="Squad name (leave blank for your squad)")
    async def squad_info(self, interaction: discord.Interaction, name: str = None):
        if name:
            row = await get_squad_by_name(name)
        else:
            row = await get_user_squad(interaction.user.id)
        if not row:
            return await interaction.response.send_message("Squad not found.", ephemeral=True)

        members = await get_squad_members(row["id"])
        owner = discord.utils.get(interaction.guild.members, id=row["owner_id"])

        embed = discord.Embed(title=f"🏆 {row['name']}", color=0x00BFFF, timestamp=datetime.utcnow())
        embed.add_field(name="Owner", value=owner.mention if owner else f"<@{row['owner_id']}>", inline=True)
        embed.add_field(name="Members", value=str(len(members)), inline=True)
        embed.add_field(name="Created", value=row["created_at"][:10], inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /squad members ────────────────────────────────────────────────────────
    @squad.command(name="members", description="List squad members")
    @app_commands.describe(name="Squad name (leave blank for your squad)")
    async def squad_members(self, interaction: discord.Interaction, name: str = None):
        if name:
            row = await get_squad_by_name(name)
        else:
            row = await get_user_squad(interaction.user.id)
        if not row:
            return await interaction.response.send_message("Squad not found.", ephemeral=True)

        members = await get_squad_members(row["id"])
        lines = []
        for m in members:
            icon = ROLE_ICONS.get(m["role"], "🛡️")
            lines.append(f"{icon} <@{m['user_id']}> — *{m['role']}*")

        embed = discord.Embed(title=f"Members of {row['name']}", description="\n".join(lines), color=0x00BFFF)
        await interaction.response.send_message(embed=embed)

    # ── /squad leaderboard ────────────────────────────────────────────────────
    @squad.command(name="leaderboard", description="Top squads by activity")
    async def squad_leaderboard(self, interaction: discord.Interaction):
        rows = await get_squad_leaderboard()
        if not rows:
            return await interaction.response.send_message("No squads yet.", ephemeral=True)
        lines = []
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        for i, r in enumerate(rows):
            icon = medals.get(i + 1, f"`#{i+1}`")
            lines.append(f"{icon} **{r['name']}** — `{r['total_messages']:,}` msgs | `{r['member_count']}` members")
        embed = discord.Embed(title="🏆 Squad Leaderboard", description="\n".join(lines), color=0x00BFFF)
        await interaction.response.send_message(embed=embed)


# ── Views ──────────────────────────────────────────────────────────────────────

class ConfirmView(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=30)
        self.author = author
        self.confirmed = False

    @discord.ui.button(label="Yes, delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        if interaction.user != self.author:
            return
        self.confirmed = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        if interaction.user != self.author:
            return
        self.stop()


class InviteView(discord.ui.View):
    def __init__(self, invitee: discord.Member, squad_id: int, squad_name: str):
        super().__init__(timeout=120)
        self.invitee = invitee
        self.squad_id = squad_id
        self.squad_name = squad_name

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.invitee:
            return await interaction.response.send_message("This invite isn't for you.", ephemeral=True)
        existing = await get_user_squad(interaction.user.id)
        if existing:
            return await interaction.response.send_message("You're already in a squad.", ephemeral=True)
        await add_squad_member(self.squad_id, interaction.user.id)
        await interaction.response.send_message(f"✅ You joined **{self.squad_name}**!")
        self.stop()

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.invitee:
            return
        await interaction.response.send_message("Invite declined.", ephemeral=True)
        self.stop()


async def setup(bot):
    await bot.add_cog(Squads(bot))