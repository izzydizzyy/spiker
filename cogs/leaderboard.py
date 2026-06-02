import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
import pytz
import asyncio
import json
import logging
import io
import urllib.request
from PIL import Image, ImageDraw, ImageFont, ImageOps

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


def fetch_avatar(url: str, size: int = 64) -> Image.Image:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = r.read()
        av = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size))
        # Circular mask
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
        av.putalpha(mask)
        return av
    except Exception:
        # Fallback: solid circle
        av = Image.new("RGBA", (size, size), (0, 77, 153, 255))
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
        av.putalpha(mask)
        return av


def render_leaderboard_image(rows_data) -> bytes:
    # rows_data: list of dicts with username, msgs, avatar_url
    COLOR_BG1    = (2, 11, 24)
    COLOR_BG2    = (6, 45, 82)
    COLOR_FOAM   = (202, 240, 248)
    COLOR_CYAN   = (144, 224, 239)
    COLOR_BLUE2  = (0, 180, 216)
    COLOR_GOLD   = (255, 215, 0)
    COLOR_SILVER = (192, 192, 192)
    COLOR_BRONZE = (205, 127, 50)
    COLOR_DIM    = (80, 130, 160)
    COLOR_CARD   = (4, 30, 54)

    W = 520
    ROW_H = 80
    HEADER_H = 52
    PAD = 24
    TOP_H = 140
    n = min(len(rows_data), 10)
    BOARD_H = HEADER_H + ROW_H * n
    H = TOP_H + BOARD_H + 60

    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # Background gradient
    for y in range(H):
        t = y / H
        r = int(COLOR_BG1[0] + (COLOR_BG2[0] - COLOR_BG1[0]) * t)
        g = int(COLOR_BG1[1] + (COLOR_BG2[1] - COLOR_BG1[1]) * t)
        b = int(COLOR_BG1[2] + (COLOR_BG2[2] - COLOR_BG1[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Fonts
    try:
        font_title  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
        font_sub    = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
        font_user   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        font_msgs   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        font_rank   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        font_hdr    = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
        font_init   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    except:
        font_title = font_sub = font_user = font_msgs = font_rank = font_hdr = font_init = ImageFont.load_default()

    # Title
    title = "Message Leaderboard"
    tw = draw.textlength(title, font=font_title)
    draw.text(((W - tw) / 2, 24), title, font=font_title, fill=COLOR_FOAM)

    eyebrow = "WEEKLY RANKINGS"
    ew = draw.textlength(eyebrow, font=font_sub)
    draw.text(((W - ew) / 2, 10), eyebrow, font=font_sub, fill=COLOR_BLUE2)

    sub = "Most active members this week"
    sw = draw.textlength(sub, font=font_sub)
    draw.text(((W - sw) / 2, 68), sub, font=font_sub, fill=COLOR_CYAN)

    # Divider
    draw.line([(PAD, 96), (W - PAD, 96)], fill=(0, 180, 216, 60), width=1)

    # Board
    bx, by = PAD, TOP_H
    bw = W - PAD * 2

    # Card bg
    draw.rectangle([bx, by, bx + bw, by + BOARD_H], fill=COLOR_CARD)
    draw.rectangle([bx, by, bx + bw, by + BOARD_H], outline=(0, 180, 216), width=1)

    # Column headers
    draw.rectangle([bx, by, bx + bw, by + HEADER_H], fill=(0, 20, 45))
    draw.text((bx + 16, by + 17), "RANK", font=font_hdr, fill=COLOR_DIM)
    draw.text((bx + 100, by + 17), "USER", font=font_hdr, fill=COLOR_DIM)
    msgs_hdr = "MESSAGES"
    mhw = draw.textlength(msgs_hdr, font=font_hdr)
    draw.text((bx + bw - 16 - mhw, by + 17), msgs_hdr, font=font_hdr, fill=COLOR_DIM)

    medal_colors = {1: COLOR_GOLD, 2: COLOR_SILVER, 3: COLOR_BRONZE}
    medal_labels = {1: "#1", 2: "#2", 3: "#3"}

    for i, row in enumerate(rows_data[:10]):
        rank = i + 1
        ry = by + HEADER_H + i * ROW_H

        # Alternate row bg
        if i % 2 == 0:
            draw.rectangle([bx, ry, bx + bw, ry + ROW_H], fill=(5, 35, 60))

        # Row border
        draw.line([(bx, ry + ROW_H), (bx + bw, ry + ROW_H)], fill=(0, 60, 90), width=1)

        # Left color strip top 3
        if rank <= 3:
            draw.rectangle([bx, ry, bx + 4, ry + ROW_H], fill=medal_colors[rank])

        # Rank badge
        badge_color = medal_colors.get(rank, COLOR_DIM)
        badge_text = medal_labels.get(rank, f"#{rank}")
        btw = draw.textlength(badge_text, font=font_rank)
        draw.text((bx + 14 + (52 - btw) / 2, ry + ROW_H // 2 - 12), badge_text,
                  font=font_rank, fill=badge_color)

        # Avatar
        av_size = 52
        av_x = bx + 72
        av_y = ry + (ROW_H - av_size) // 2
        av_img = row.get("avatar_img")
        if av_img:
            resized = av_img.resize((av_size, av_size))
            img.paste(resized, (av_x, av_y), resized)
        else:
            draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], fill=(0, 77, 153))
            initials = row["username"][:2].upper()
            iw = draw.textlength(initials, font=font_init)
            draw.text((av_x + (av_size - iw) / 2, av_y + 16), initials, font=font_init, fill=COLOR_FOAM)

        # Username
        uname_color = (255, 255, 255) if rank == 1 else COLOR_FOAM
        draw.text((bx + 136, ry + ROW_H // 2 - 12), row["username"], font=font_user, fill=uname_color)

        # Message count
        msg_text = f"{row['msgs']:,}"
        mtw = draw.textlength(msg_text, font=font_msgs)
        draw.text((bx + bw - 16 - mtw, ry + ROW_H // 2 - 12), msg_text, font=font_msgs, fill=COLOR_CYAN)

    # Footer
    footer = "RESETS EVERY TUESDAY  ·  7:30 AM ET"
    fw = draw.textlength(footer, font=font_sub)
    draw.text(((W - fw) / 2, by + BOARD_H + 16), footer, font=font_sub, fill=COLOR_DIM)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


async def build_leaderboard_image(bot, rows) -> bytes:
    # Fetch avatars concurrently
    async def get_avatar(row):
        try:
            user = await bot.fetch_user(int(row["user_id"]))
            url = str(user.display_avatar.with_size(64).url)
            av_img = await asyncio.to_thread(fetch_avatar, url, 64)
        except Exception:
            av_img = None
        return {**row, "avatar_img": av_img}

    rows_with_avatars = await asyncio.gather(*[get_avatar(r) for r in rows])
    return await asyncio.to_thread(render_leaderboard_image, rows_with_avatars)


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
            img_bytes = await build_leaderboard_image(self.bot, rows)
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