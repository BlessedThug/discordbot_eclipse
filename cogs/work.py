import discord
from discord.ext import commands
from discord import app_commands
import time
import random

from utils import data as db

WORK_COOLDOWN = 3600
MIN_REWARD = 100
MAX_REWARD = 1000


class WorkCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="work", description="Заработать деньги (раз в час)")
    async def work(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        gid = interaction.guild.id
        
        profile = db.get_profile(gid, interaction.user.id)
        if profile is None:
            await interaction.response.send_message(
                "❌ Вы ещё не зарегистрированы. Используйте `/reg`, чтобы создать профиль.",
                ephemeral=True,
            )
            return

        now = int(time.time())
        last = profile.get("last_work", 0)
        if now - last < WORK_COOLDOWN:
            remaining = WORK_COOLDOWN - (now - last)
            await interaction.response.send_message(
                f"⏳ Вы уже работали. Отдохните ещё **{remaining // 60} мин {remaining % 60} сек**.",
                ephemeral=True,
            )
            return

        reward = random.randint(MIN_REWARD, MAX_REWARD)
        is_vip = db.has_active_status(profile, "VIP")
        if is_vip:
            reward *= 2

        profile["balance"] = profile.get("balance", 0) + reward
        profile["last_work"] = now
        
        db.update_profile(gid, interaction.user.id, profile)

        description = f"Вы поработали и заработали **{reward} ₽**!"
        if is_vip:
            description += "\n✨ **VIP x2**"

        embed = discord.Embed(
            title="💼 Работа",
            description=description,
            color=discord.Color.gold() if is_vip else discord.Color.green(),
        )
        embed.set_footer(text="Возвращайтесь через час!")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(WorkCog(bot))