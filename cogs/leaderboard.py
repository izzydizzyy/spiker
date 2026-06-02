import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
import pytz
import asyncio
import json
import logging
import io
from PIL import Image, ImageDraw, ImageFont

from utils.database import get_leaderboard, get_user_rank, reset_weekly

log = logging.getLogger("leaderboard")

RESET_DAY = 1
RESET_TIME = time(hour=7, minute=30)
TIMEZONE = pytz.timezone("US/Eastern")

ws_clients: set = set()

async def broadcast_leaderboard():
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


def render_leaderboard_image(rows) -> bytes:
    # Colors
    BG_TOP       = (2, 11, 24)
    BG_BOT       = (6, 45, 82)
    CARD_BG      = (4, 30, 54, 210)
    BORDER       = (0, 180, 216, 50)
    HEADER_BG    = (0, 119, 204, 20)
    ROW_BORDER   = (0, 180, 216, 15)
    COLOR_FOAM   = (202, 240, 248)
    COLOR_CYAN   = (144, 224, 239)
    COLOR_BLUE2  = (0, 180, 216)
    COLOR_GOLD   = (255, 215, 0)
    COLOR_SILVER = (192, 192, 192)
    COLOR_BRONZE = (205, 127, 50)
    COLOR_DIM    = (100, 160, 190)

    W = 760
    ROW_H = 64
    HEADER_H = 48
    TOP_PAD = 80
    BOTTOM_PAD = 48
    BOARD_PAD = 32

    n = min(len(rows), 10)
    BOARD_H = HEADER_H + ROW_H * n
    H = TOP_PAD + 110 + BOARD_H + BOTTOM_PAD

    # Background gradient
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        r = int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Fonts — fallback to default if not found
    try:
        font_big   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        font_med   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        font_rank  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 17)
    except:
        font_big = font_med = font_small = font_rank = ImageFont.load_default()

    # Header text
    eyebrow = "WEEKLY RANKINGS"
    ew = draw.textlength(eyebrow, font=font_small)
    draw.text(((W - ew) / 2, 28), eyebrow, font=font_small, fill=COLOR_BLUE2)

    title = "Message Leaderboard"
    tw = draw.textlength(title, font=font_big)
    draw.text(((W - tw) / 2, 48), title, font=font_big, fill=COLOR_FOAM)

    sub = "Most active members this week"
    sw = draw.textlength(sub, font=font_small)
    draw.text(((W - sw) / 2, 92), sub, font=font_small, fill=COLOR_CYAN)

    # Board card
    board_x = BOARD_PAD
    board_y = TOP_PAD + 110
    board_w = W - BOARD_PAD * 2

    # Card background
    card = Image.new("RGBA", (board_w, BOARD_H), CARD_BG)
    img.paste(Image.new("RGB", (board_w, BOARD_H), (4, 30, 54)), (board_x, board_y),
              Image.new("L", (board_w, BOARD_H), 210))

    draw = ImageDraw.Draw(img)

    # Card border
    draw.rectangle([board_x, board_y, board_x + board_w, board_y + BOARD_H],
                   outline=(0, 180, 216, 50), width=1)

    # Column header
    draw.rectangle([board_x, board_y, board_x + board_w, board_y + HEADER_H],
                   fill=(0, 30, 60))
    draw.text((board_x + 20, board_y + 16), "RANK", font=font_small, fill=COLOR_DIM)
    draw.text((board_x + 80, board_y + 16), "USER", font=font_small, fill=COLOR_DIM)
    msg_label = "MESSAGES"
    mlw = draw.textlength(msg_label, font=font_small)
    draw.text((board_x + board_w - 24 - mlw, board_y + 16), msg_label, font=font_small, fill=COLOR_DIM)

    # Rows
    medal_colors = {1: COLOR_GOLD, 2: COLOR_SILVER, 3: COLOR_BRONZE}
    medal_labels = {1: "#1", 2: "#2", 3: "#3"}

    for i, row in enumerate(rows[:10]):
        rank = i + 1
        ry = board_y + HEADER_H + i * ROW_H

        # Row border bottom
        draw.line([(board_x, ry + ROW_H), (board_x + board_w, ry + ROW_H)],
                  fill=(0, 180, 216, 15))

        # Left color strip for top 3
        if rank <= 3:
            strip_color = medal_colors[rank]
            draw.rectangle([board_x, ry, board_x + 3, ry + ROW_H], fill=strip_color)

        # Rank badge
        badge_color = medal_colors.get(rank, COLOR_DIM)
        badge_text = medal_labels.get(rank, f"#{rank}")
        btw = draw.textlength(badge_text, font=font_rank)
        draw.text((board_x + 28 - btw / 2, ry + ROW_H // 2 - 10), badge_text,
                  font=font_rank, fill=badge_color)

        # Avatar circle
        av_x, av_y = board_x + 76, ry + ROW_H // 2
        draw.ellipse([av_x - 18, av_y - 18, av_x + 18, av_y + 18], fill=(0, 77, 153))
        initials = row["username"][:2].upper()
        iw = draw.textlength(initials, font=font_small)
        draw.text((av_x - iw / 2, av_y - 8), initials, font=font_small, fill=COLOR_FOAM)

        # Username
        uname_color = (255, 255, 255) if rank == 1 else COLOR_FOAM
        draw.text((board_x + 104, ry + ROW_H // 2 - 10), row["username"],
                  font=font_med, fill=uname_color)

        # Message count
        msg_text = f"{row['msgs']:,}"
        mtw = draw.textlength(msg_text, font=font_rank)
        draw.text((board_x + board_w - 24 - mtw, ry + ROW_H // 2 - 10),
                  msg_text, font=font_rank, fill=COLOR_CYAN)

    # Footer
    footer = "RESETS EVERY TUESDAY  ·  7:30 AM ET"
    fw = draw.textlength(footer, font=font_small)
    draw.text(((W - fw) / 2, board_y + BOARD_H + 16), footer, font=font_small, fill=COLOR_DIM)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.weekly_reset.start()

    def cog_unload(self):
        self.weekly_reset.cancel()

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

    @app_commands.command(name="leaderboard", description="View the weekly message leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()

        rows = await get_leaderboard(limit=10)

        if not rows:
            await interaction.followup.send("No messages tracked yet!", ephemeral=True)
            return

        try:
            img_bytes = await asyncio.to_thread(render_leaderboard_image, rows)
            file = discord.File(io.BytesIO(img_bytes), filename="leaderboard.png")
            await interaction.followup.send(file=file)
        except Exception as e:
            log.error(f"Image render failed: {e}")
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