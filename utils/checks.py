import discord
from discord import app_commands
from functools import wraps

# Staff role names — adjust to match your server
STAFF_ROLE_NAMES = {"Staff", "Moderator", "Admin", "Owner"}

def is_staff():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        roles = {r.name for r in interaction.user.roles}
        if roles & STAFF_ROLE_NAMES:
            return True
        await interaction.response.send_message(
            "❌ You don't have permission to use this command.", ephemeral=True
        )
        return False
    return app_commands.check(predicate)