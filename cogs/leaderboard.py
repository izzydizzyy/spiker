import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
import pytz
import asyncio
import json
import logging
import io

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


async def screenshot_leaderboard(rows) -> bytes:
    """Render the leaderboard as HTML and screenshot it with Playwright."""
    from playwright.async_api import async_playwright

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    rows_html = ""
    for i, row in enumerate(rows[:10]):
        rank = i + 1
        medal = medals.get(rank, f"#{rank}")
        rank_class = f"rank-{rank}" if rank <= 3 else ""
        badge_class = f"top{rank}" if rank <= 3 else ""
        initials = row["username"][:2].upper()
        rows_html += f"""
        <div class="row {rank_class}">
            <div class="rank-badge {badge_class}">{medal}</div>
            <div class="user-info">
                <div class="avatar">{initials}</div>
                <span class="username">{row["username"]}</span>
            </div>
            <div class="msg-count">{row["msgs"]:,}</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8"/>
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=Exo+2:wght@400;600;700&display=swap" rel="stylesheet"/>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --deep: #020b18; --mid: #041e36; --surface: #062d52;
    --blue1: #0077cc; --blue2: #00b4d8; --cyan: #90e0ef; --foam: #caf0f8;
    --gold: #ffd700; --silver: #c0c0c0; --bronze: #cd7f32;
  }}
  body {{
    background: linear-gradient(180deg, #020b18 0%, #031526 40%, #041e36 70%, #062d52 100%);
    color: var(--foam); font-family: 'Exo 2', sans-serif;
    width: 760px; padding: 40px 32px 48px;
  }}
  .header {{ text-align: center; margin-bottom: 28px; }}
  .eyebrow {{ font-family: 'Rajdhani', sans-serif; font-size: 11px; letter-spacing: 5px;
    text-transform: uppercase; color: var(--blue2); margin-bottom: 8px; }}
  .title {{ font-family: 'Rajdhani', sans-serif; font-size: 48px; font-weight: 700;
    background: linear-gradient(135deg, var(--foam) 0%, var(--cyan) 50%, var(--blue2) 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
  .sub {{ font-size: 13px; color: var(--cyan); opacity: .7; margin-top: 8px; letter-spacing: 1px; }}
  .board {{ background: rgba(4,30,54,0.85); border: 1px solid rgba(0,180,216,0.2);
    border-radius: 16px; overflow: hidden; }}
  .board-header {{ display: grid; grid-template-columns: 56px 1fr auto;
    padding: 14px 24px; border-bottom: 1px solid rgba(0,180,216,0.12);
    background: rgba(0,119,204,.08); }}
  .board-header span {{ font-family: 'Rajdhani', sans-serif; font-size: 11px;
    letter-spacing: 3px; text-transform: uppercase; color: var(--blue2); opacity: .6; }}
  .board-header span:last-child {{ text-align: right; }}
  .row {{ display: grid; grid-template-columns: 56px 1fr auto; align-items: center;
    padding: 0 24px; height: 64px; border-bottom: 1px solid rgba(0,180,216,0.06);
    position: relative; }}
  .row:last-child {{ border-bottom: none; }}
  .row.rank-1::before {{ content:''; position:absolute; left:0; top:0; bottom:0; width:3px;
    background: var(--gold); box-shadow: 0 0 12px var(--gold); }}
  .row.rank-2::before {{ content:''; position:absolute; left:0; top:0; bottom:0; width:3px;
    background: var(--silver); box-shadow: 0 0 12px var(--silver); }}
  .row.rank-3::before {{ content:''; position:absolute; left:0; top:0; bottom:0; width:3px;
    background: var(--bronze); box-shadow: 0 0 12px var(--bronze); }}
  .rank-badge {{ font-family: 'Rajdhani', sans-serif; font-size: 18px; font-weight: 700;
    text-align: center; color: rgba(144,224,239,.35); }}
  .rank-badge.top1 {{ color: var(--gold); }} .rank-badge.top2 {{ color: var(--silver); }}
  .rank-badge.top3 {{ color: var(--bronze); }}
  .user-info {{ display: flex; align-items: center; gap: 12px; }}
  .avatar {{ width: 36px; height: 36px; border-radius: 50%;
    background: linear-gradient(135deg, var(--blue1), var(--blue2));
    display: flex; align-items: center; justify-content: center;
    font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 14px;
    color: var(--foam); border: 1px solid rgba(144,224,239,.2); }}
  .username {{ font-size: 15px; font-weight: 600; color: var(--foam); }}
  .row.rank-1 .username {{ color: #fff; }}
  .msg-count {{ font-family: 'Rajdhani', sans-serif; font-size: 17px; font-weight: 700;
    color: var(--cyan); text-align: right; }}
  .footer {{ text-align: center; margin-top: 20px; font-size: 11px; color: var(--cyan);
    opacity: .3; letter-spacing: 2px; text-transform: uppercase; }}
</style>
</head>
<body>
  <div class="header">
    <div class="eyebrow">Weekly Rankings</div>
    <div class="title">Message Leaderboard</div>
    <div class="sub">Most active members this week</div>
  </div>
  <div class="board">
    <div class="board-header">
      <span>Rank</span><span>User</span><span>Messages</span>
    </div>
    {rows_html}
  </div>
  <div class="footer">Resets every Tuesday · 7:30 AM ET</div>
</body>
</html>"""

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 760, "height": 800})
        await page.set_content(html, wait_until="networkidle")
        screenshot = await page.screenshot(full_page=True)
        await browser.close()
        return screenshot


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
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()

        rows = await get_leaderboard(limit=10)

        if not rows:
            await interaction.followup.send("No messages tracked yet!", ephemeral=True)
            return

        try:
            screenshot = await screenshot_leaderboard(rows)
            file = discord.File(io.BytesIO(screenshot), filename="leaderboard.png")
            await interaction.followup.send(file=file)
        except Exception as e:
            log.error(f"Screenshot failed: {e}")
            # Fallback to embed if screenshot fails
            embed = discord.Embed(
                title="💬 Weekly Message Leaderboard",
                description="Resets every **Tuesday at 7:30 AM ET**",
                color=0x00BFFF,
                timestamp=datetime.utcnow()
            )
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            lines = []
            for i, row in enumerate(rows):
                rank = i + 1
                icon = medals.get(rank, f"`#{rank}`")
                lines.append(f"{icon} **{row['username']}** — `{row['msgs']:,}` msgs")
            embed.description = (embed.description or "") + "\n\n" + "\n".join(lines)
            await interaction.followup.send(embed=embed)

        await broadcast_leaderboard()

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


async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboard(bot))