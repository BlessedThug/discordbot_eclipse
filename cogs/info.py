import discord
from discord.ext import commands
from discord import app_commands


class InfoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="info", description="Справочник по всем командам и возможностям")
    async def info(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="❓ Справочник команд",
            description="Все команды работают на сервере, где зарегистрирован бот.",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="👤 Профиль и баланс",
            value=(
                "`/reg` — зарегистрироваться в системе\n"
                "`/profile [@user]` — профиль (свой или другого)\n"
                "`/bal [@user]` — баланс\n"
                "`/inv [@user]` — инвентарь\n"
                "`/baltop` — топ-10 богачей сервера\n"
                "`/honors [@user]` — все почести игрока"
            ),
            inline=False,
        )

        embed.add_field(
            name="🎁 Кейсы и награды",
            value=(
                "`/dc` — открыть ежедневный кейс (раз в 12 ч)\n"
                "`/open <кейс> [кол-во]` — платный кейс по ключу (до 10 за раз)"
            ),
            inline=False,
        )

        embed.add_field(
            name="💼 Заработок",
            value=(
                "`/work` — заработать деньги (раз в час)\n"
                "`/calendar` — ежедневный календарь на 28 дней\n"
                "`/dc` — ежедневный кейс (стрик повышает награду)"
            ),
            inline=False,
        )

        embed.add_field(
            name="🏪 Экономика",
            value=(
                "`/shop` — магазин сервера и рынок игроков\n"
                "`/sell <предмет> <цена>` — выставить предмет на рынок\n"
                "`/gift @user <сумма|предмет>` — подарить\n"
                "`/use <предмет>` — использовать функциональный предмет"
            ),
            inline=False,
        )

        embed.add_field(
            name="🎮 Азартные игры",
            value=(
                "`/bet slots <сумма>` — 🎰 слоты\n"
                "`/bet wheel <сумма>` — 🎡 колесо фортуны\n"
                "`/bet blackjack <сумма>` — 🃏 блэкджек\n"
                "`/bet coin <сумма>` — 🪙 орёл или решка\n"
                "*Мин. ставка 100 ₽, макс. 1 000 000 ₽*"
            ),
            inline=False,
        )

        if interaction.user.guild_permissions.administrator:
            embed.add_field(
                name="🛡️ Для администраторов",
                value=(
                    "`/money give|take|set @user <сумма>` — управление балансом\n"
                    "`/item give|take @user <предмет> [кол-во] [цена] [описание]`\n"
                    "`/item_delete <предмет>` — удалить предмет из каталога\n"
                    "`/lvl give|take|set @user <уровень>` — уровни\n"
                    "`/status set|add|remove @user <имя> [приоритет] [дни]`\n"
                    "`/honor add|remove @user <имя> [описание] [иконка]`\n"
                    "`/sync_ranks` — синхронизировать ранговые роли\n"
                    "`/shop_pool add|remove|list [предмет] [min] [max]`\n"
                    "`/season_reset [год]` — ежегодный сброс уровней\n"
                    "`/unreg @user` — удалить игрока из системы"
                ),
                inline=False,
            )

        embed.set_footer(text="Подсказка: параметры в [скобках] необязательны")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(InfoCog(bot))