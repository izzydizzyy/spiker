import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import logging
from utils.database import save_report

log = logging.getLogger("reports")

REPORT_CHANNEL_ID = 1492854203587100772

class Reports(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="staff-report", description="Submit a report to staff")
    @app_commands.checks.cooldown(1, 60)
    async def staff_report(self, interaction: discord.Interaction):
        view = ReportTypeView(interaction.user)
        await interaction.response.send_message(
            "Select the type of report you'd like to submit:",
            view=view,
            ephemeral=True
        )


class ReportTypeView(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=60)
        self.author = author

    @discord.ui.select(
        placeholder="Choose report type...",
        options=[
            discord.SelectOption(label="Player Report", value="player", emoji="👤"),
            discord.SelectOption(label="Moderator Report", value="moderator", emoji="🛡️"),
            discord.SelectOption(label="Other Report", value="other", emoji="📋"),
        ]
    )
    async def select_type(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user != self.author:
            return
        report_type = select.values[0].capitalize()
        await interaction.response.send_modal(ReportModal(report_type))


class ReportModal(discord.ui.Modal):
    def __init__(self, report_type: str):
        super().__init__(title=f"Submit {report_type} Report")
        self.report_type = report_type

        self.reported_user = discord.ui.TextInput(
            label="Reported User (Username or ID)",
            placeholder="e.g. username#0000",
            max_length=100
        )
        self.reason = discord.ui.TextInput(
            label="Reason",
            placeholder="Why are you reporting this person?",
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.evidence = discord.ui.TextInput(
            label="Evidence (link, screenshot URL, etc.)",
            placeholder="Provide any links to evidence",
            required=False,
            max_length=500
        )
        self.extra_info = discord.ui.TextInput(
            label="Additional Information",
            placeholder="Anything else staff should know?",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=500
        )
        self.add_item(self.reported_user)
        self.add_item(self.reason)
        self.add_item(self.evidence)
        self.add_item(self.extra_info)

    async def on_submit(self, interaction: discord.Interaction):
        report_id = await save_report(
            interaction.user.id,
            str(interaction.user),
            self.report_type,
            self.reported_user.value,
            self.reason.value,
            self.evidence.value or "None provided",
            self.extra_info.value or "None"
        )

        embed = discord.Embed(
            title=f"📋 New {self.report_type} Report",
            color=0xFF4444,
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Reporter", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name="Type", value=self.report_type, inline=True)
        embed.add_field(name="Reported User", value=self.reported_user.value, inline=True)
        embed.add_field(name="Reason", value=self.reason.value, inline=False)
        embed.add_field(name="Evidence", value=self.evidence.value or "None provided", inline=False)
        embed.add_field(name="Additional Info", value=self.extra_info.value or "None", inline=False)
        embed.set_footer(text=f"Report ID: #{report_id}")

        channel = interaction.client.get_channel(REPORT_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed)
            await interaction.response.send_message("✅ Your report has been submitted. Staff will review it shortly.", ephemeral=True)
        else:
            log.error(f"Report channel {REPORT_CHANNEL_ID} not found")
            await interaction.response.send_message("✅ Report logged, but I couldn't find the staff channel. Please contact a moderator directly.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Reports(bot))