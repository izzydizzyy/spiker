import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
import pytz
import asyncio
import json
import logging

from utils.database import get_leaderboard, get_user_rank, reset_weekly

log = logging.getLogger("leaderboard")

# Tuesday = weekday 1, at 7:30 AM ET
RESET_DAY = 1   # Tuesday
RESET_TIME = time(hour=7, minute=30)
TIMEZONE = pytz.timezone("US/Eastern")

# Shared set of active WebSocket connections (populated by web/server.py)
ws_clients: set = set()

async def broadcast_leaderboard():
    """Push fresh leaderboard data to all connected web clients."""
    if not ws_clients:
        return
    rows = await get_leaderboard(limit=25)
    payload = json.dumps([
        {"rank": i + 1, "username": r["username"], "msgs": r["msgs"]}
        for i, r in enumerate(rows)
    ])
    dead = set()
    for ws in ws_clients:
        try:
            await ws.send(payload)
        except Exception:
            dead.add(ws)
    ws_clients -= dead


class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.weekly_reset.start()

    def cog_unload(self):
        self.weekly_reset.cancel()

    # ── Weekly reset loop ──────────────────────────────────────────────────────
    @tasks.loop(minutes=1)
    async def weekly_reset(self):
        now = datetime.now(TIMEZONE)
        if now.weekday() == RESET_DAY and now.hour == RESET_TIME.hour and now.minute == RESET_TIME.minute:
            await reset_weekly()
            await broadcast_leaderboard()
            log.info("Weekly leaderboard reset complete")

    @weekly_reset.before_loop
    async def before_reset(self):
        await self.bot.wait_until_ready()

    # ── /leaderboard ───────────────────────────────────────────────────────────
    @app_commands.command(name="leaderboard", description="View the weekly message leaderboard")
    @app_commands.describe(page="Page number (10 per page)")
    async def leaderboard(self, interaction: discord.Interaction, page: int = 1):
        await interaction.response.defer()

        per_page = 10
        offset = (page - 1) * per_page
        rows = await get_leaderboard(limit=100)

        if not rows:
            await interaction.followup.send("No messages tracked yet!", ephemeral=True)
            return

        total_pages = max(1, (len(rows) + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        slice_ = rows[offset: offset + per_page]

        embed = discord.Embed(
            title="💬 Weekly Message Leaderboard",
            description="Resets every **Tuesday at 7:30 AM ET**",
            color=0x00BFFF,
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Page {page}/{total_pages} • Weekly Reset: Tuesday 7:30 AM ET")

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for i, row in enumerate(slice_):
            rank = offset + i + 1
            icon = medals.get(rank, f"`#{rank}`")
            lines.append(f"{icon} **{row['username']}** — `{row['msgs']:,}` msgs")

        embed.description = (embed.description or "") + "\n\n" + "\n".join(lines)

        view = LeaderboardPager(page, total_pages, interaction.user)
        await interaction.followup.send(embed=embed, view=view)

    # ── /rank ──────────────────────────────────────────────────────────────────
    @app_commands.command(name="rank", description="Check your or another user's rank")
    @app_commands.describe(user="User to check (defaults to you)")
    async def rank(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        row = await get_user_rank(target.id)

        if not row or row["msgs"] == 0:
            await interaction.response.send_message(
                f"{'You have' if target == interaction.user else f'{target.display_name} has'} no messages tracked yet.",
                ephemeral=True
            )
            return

        embed = discord.Embed(color=0x00BFFF)
        embed.set_author(name=f"{target.display_name}'s Rank", icon_url=target.display_avatar.url)
        embed.add_field(name="Rank", value=f"**#{row['rank']}**", inline=True)
        embed.add_field(name="Messages (Week)", value=f"`{row['msgs']:,}`", inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /messages ─────────────────────────────────────────────────────────────
    @app_commands.command(name="messages", description="See your total message count")
    async def messages(self, interaction: discord.Interaction):
        row = await get_user_rank(interaction.user.id, weekly=False)
        week_row = await get_user_rank(interaction.user.id, weekly=True)
        embed = discord.Embed(title="Your Message Stats", color=0x00BFFF)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="Total Messages", value=f"`{row['msgs']:,}`" if row else "`0`", inline=True)
        embed.add_field(name="This Week", value=f"`{week_row['msgs']:,}`" if week_row else "`0`", inline=True)
        await interaction.response.send_message(embed=embed)


class LeaderboardPager(discord.ui.View):
    def __init__(self, current_page: int, total_pages: int, author: discord.User):
        super().__init__(timeout=60)
        self.current_page = current_page
        self.total_pages = total_pages
        self.author = author
        self._update_buttons()

    def _update_buttons(self):
        self.prev_btn.disabled = self.current_page <= 1
        self.next_btn.disabled = self.current_page >= self.total_pages

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.blurple)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your leaderboard.", ephemeral=True)
        self.current_page -= 1
        await self._refresh(interaction)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.blurple)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your leaderboard.", ephemeral=True)
        self.current_page += 1
        await self._refresh(interaction)

    async def _refresh(self, interaction: discord.Interaction):
        self._update_buttons()
        per_page = 10
        offset = (self.current_page - 1) * per_page
        rows = await get_leaderboard(limit=100)
        slice_ = rows[offset: offset + per_page]

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for i, row in enumerate(slice_):
            rank = offset + i + 1
            icon = medals.get(rank, f"`#{rank}`")
            lines.append(f"{icon} **{row['username']}** — `{row['msgs']:,}` msgs")

        embed = discord.Embed(
            title="💬 Weekly Message Leaderboard",
            description="Resets every **Tuesday at 7:30 AM ET**\n\n" + "\n".join(lines),
            color=0x00BFFF,
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Page {self.current_page}/{self.total_pages} • Weekly Reset: Tuesday 7:30 AM ET")
        await interaction.response.edit_message(embed=embed, view=self)


async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboard(bot))