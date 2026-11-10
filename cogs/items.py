import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Optional

from utils import data as db
from utils import levels as lv


class ItemsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def item_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        if interaction.guild is None: return []
        profile = db.get_profile(interaction.guild.id, interaction.user.id)
        if not profile: return []
        inventory = profile.get("inventory", [])
        matches = [item for item in inventory if current.lower() in item.lower()]
        return [app_commands.Choice(name=item, value=item) for item in matches[:25]]

    @app_commands.command(name="use", description="Использовать функциональный предмет из инвентаря")
    @app_commands.autocomplete(item=item_autocomplete)
    async def use_item(self, interaction: discord.Interaction, item: str):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        gid = interaction.guild.id
        profile = db.get_profile(gid, interaction.user.id)
        if profile is None:
            await interaction.response.send_message("❌ Вы не зарегистрированы.", ephemeral=True)
            return

        inventory = profile.get("inventory", [])
        if item not in inventory:
            await interaction.response.send_message(f"❌ У вас нет предмета `{item}`.", ephemeral=True)
            return

        items_data = db.load_items(gid)
        item_info = items_data.get(item)
        if not item_info:
            await interaction.response.send_message("❌ Информация о предмете не найдена.", ephemeral=True)
            return

        item_type = item_info.get("type")
        effect = item_info.get("effect") or {}

        if item_type == "boost" and "level" in effect:
            old = profile.get("level", 0)
            
            # Используем функцию без возможности стать легендарным
            new = lv.apply_level_change_no_legend(old, effect["level"])
            
            if new == old:
                await interaction.response.send_message(
                    "❌ Вы достигли Легендарного ранга (999+). Бусты уровней больше не действуют.",
                    ephemeral=True
                )
                return

            profile["level"] = new
            inventory.remove(item)
            profile["inventory"] = inventory
            db.update_profile(gid, interaction.user.id, profile)

            member = interaction.guild.get_member(interaction.user.id)
            if member is None:
                try: member = await interaction.guild.fetch_member(interaction.user.id)
                except Exception: member = None
            if member:
                await lv.sync_rank_roles(interaction.guild, member, old, new)

            gained = new - old
            note = "\n⚠️ Достигнут потолок 999 (Абсолют)." if new == 999 else ""
            await interaction.response.send_message(
                f"✅ Вы использовали **{item}**! Уровень повышен на {gained}. Текущий уровень: {new}.{note}"
            )
            return

        if item_type == "key":
            await interaction.response.send_message("❌ Это ключ от кейса. Используйте `/open`.", ephemeral=True)
            return

        await interaction.response.send_message(f"❌ Предмет `{item}` нельзя использовать.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ItemsCog(bot))