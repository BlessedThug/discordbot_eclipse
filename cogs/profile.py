import discord
from discord.ext import commands
from discord import app_commands
import time
from typing import List, Optional
from collections import Counter

from utils import data as db
from utils import levels as lv

NOT_REGISTERED_MSG = (
    "❌ Вы ещё не зарегистрированы. Используйте команду `/reg`, чтобы создать профиль."
)


def build_honors_embed(target: discord.User, honors: list) -> discord.Embed:
    embed = discord.Embed(
        title=f"🏅 Почести {target.display_name}",
        color=discord.Color.gold(),
    )
    embed.set_thumbnail(url=target.display_avatar.url)

    if not honors:
        embed.description = "*Пока нет ни одной почести.*"
        return embed

    lines = []
    for h in honors:
        icon = h.get("icon", "🏅")
        name = h.get("name", "Без названия")
        desc = h.get("description", "")
        date_ts = h.get("date")
        line = f"{icon} **{name}**"
        if desc:
            line += f"\n> *{desc}*"
        if date_ts:
            line += f"\n-# <t:{date_ts}:d>"
        lines.append(line)

    embed.description = "\n\n".join(lines)
    embed.set_footer(text=f"Всего почестей: {len(honors)}")
    return embed


class ProfileActionsView(discord.ui.View):
    def __init__(self, guild_id: int, target: discord.User, honors_count: int):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.target = target
        self.honors_button.label = f"🏅 Почести ({honors_count})"

    @discord.ui.button(label="🏅 Почести", style=discord.ButtonStyle.secondary)
    async def honors_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        profile = db.get_profile(self.guild_id, self.target.id)
        honors = profile.get("honors", []) if profile else []
        embed = build_honors_embed(self.target, honors)
        await interaction.response.send_message(embed=embed)


class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _check_guild(self, interaction: discord.Interaction) -> Optional[int]:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Команда доступна только на сервере.", ephemeral=True
            )
            return None
        return interaction.guild.id

    async def _not_registered(self, interaction: discord.Interaction, target: discord.User) -> bool:
        if target.id == interaction.user.id:
            await interaction.response.send_message(NOT_REGISTERED_MSG, ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Пользователь **{target.display_name}** не зарегистрирован на этом сервере.",
                ephemeral=True,
            )
        return True

    def _get_highest_status(self, guild_id: int, user_id: int) -> str:
        profile = db.get_profile(guild_id, user_id)
        if not profile:
            return "Не зарегистрирован"
        now = int(time.time())
        active = [
            s for s in profile.get("statuses", [])
            if s.get("expiry", 0) == 0 or s["expiry"] > now
        ]
        if not active:
            return "Участник"
        return max(active, key=lambda x: x.get("priority", 0))["name"]

    def _get_place_in_top(self, guild_id: int, user_id: int) -> int:
        profiles = db.load_profiles(guild_id)
        sorted_users = sorted(
            profiles.items(), key=lambda x: x[1].get("balance", 0), reverse=True
        )
        for i, (uid, _) in enumerate(sorted_users, start=1):
            if int(uid) == user_id:
                return i
        return 0

    def _get_inventory_value(self, guild_id: int, user_id: int) -> int:
        profile = db.get_profile(guild_id, user_id)
        if not profile:
            return 0
        items = db.load_items(guild_id)
        return sum(items.get(name, {}).get("base_price", 0) for name in profile.get("inventory", []))

    # ---------- /reg ----------
    @app_commands.command(name="reg", description="Зарегистрироваться в системе")
    async def register(self, interaction: discord.Interaction):
        gid = await self._check_guild(interaction)
        if gid is None:
            return

        if db.get_profile(gid, interaction.user.id) is not None:
            await interaction.response.send_message("✅ Вы уже зарегистрированы!", ephemeral=True)
            return

        db.create_profile_if_missing(gid, interaction.user.id)

        embed = discord.Embed(
            title="🎉 Добро пожаловать!",
            description=(
                f"Привет, **{interaction.user.display_name}**! Вы успешно зарегистрированы.\n\n"
                "**Быстрый старт:**\n"
                "• 💰 `/bal` — проверить баланс\n"
                "• 🎒 `/inv` — открыть инвентарь\n"
                "• 👤 `/profile` — посмотреть профиль\n"
                "• 🏅 `/honors` — посмотреть почести\n"
                "• 🎁 `/dc` — забрать ежедневный кейс (раз в 12 ч)\n"
                "• 💼 `/work` — заработать деньги (раз в час)\n"
                "• 🏪 `/shop` — магазин и рынок\n"
                "• 🎁 `/gift` — подарить другому игроку\n"
                "• ❓ `/info` — полный справочник команд"
            ),
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Удачи в игре!")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------- /bal ----------
    @app_commands.command(name="bal", description="Показать баланс")
    async def balance(self, interaction: discord.Interaction, user: discord.User = None):
        gid = await self._check_guild(interaction)
        if gid is None:
            return

        target = user or interaction.user
        profile = db.get_profile(gid, target.id)
        if profile is None:
            await self._not_registered(interaction, target)
            return

        embed = discord.Embed(title="💰 Баланс", color=discord.Color.green())
        embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
        embed.add_field(name="Сумма", value=f"**{profile.get('balance', 0)} ₽**", inline=False)
        await interaction.response.send_message(embed=embed)

    # ---------- /inv ----------
    @app_commands.command(name="inv", description="Показать инвентарь")
    async def inventory(self, interaction: discord.Interaction, user: discord.User = None):
        gid = await self._check_guild(interaction)
        if gid is None:
            return

        target = user or interaction.user
        profile = db.get_profile(gid, target.id)
        if profile is None:
            await self._not_registered(interaction, target)
            return

        inventory = profile.get("inventory", [])
        if not inventory:
            await interaction.response.send_message(f"Инвентарь **{target.display_name}** пуст.")
            return

        total_value = self._get_inventory_value(gid, target.id)
        items_data = db.load_items(gid)
        view = InventoryPaginator(inventory, total_value, len(inventory), target.id, items_data)
        embed, _ = view.get_page(0)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    # ---------- /profile ----------
    @app_commands.command(name="profile", description="Показать профиль")
    async def profile(self, interaction: discord.Interaction, user: discord.User = None):
        gid = await self._check_guild(interaction)
        if gid is None:
            return

        target = user or interaction.user
        profile = db.get_profile(gid, target.id)
        if profile is None:
            await self._not_registered(interaction, target)
            return

        status = self._get_highest_status(gid, target.id)
        level = profile.get("level", 0)
        rank = lv.get_rank_name(level)
        balance = profile.get("balance", 0)
        inv_value = self._get_inventory_value(gid, target.id)
        total_items = len(profile.get("inventory", []))
        honors_count = len(profile.get("honors", []))
        place = self._get_place_in_top(gid, target.id)

        if "Разработчик" in status:
            color = discord.Color.purple()
        elif "VIP" in status:
            color = discord.Color.gold()
        else:
            color = discord.Color.teal()

        embed = discord.Embed(
            title="👤 Профиль игрока",
            description=f"**{target.display_name}**\n─────────────────",
            color=color,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(name="🏷️ Статус", value=f"⭐ **{status}**\n\u200b", inline=False)
        embed.add_field(name="🏅 Ранг", value=f"**{rank}**\n\u200b", inline=False)
        embed.add_field(name="📊 Уровень", value=f"**{level}**\n\u200b", inline=False)
        embed.add_field(name="💰 Баланс", value=f"**{balance} ₽**\n\u200b", inline=False)
        embed.add_field(name="🏆 Место в топе", value=f"**#{place}**\n\u200b", inline=False)
        embed.add_field(
            name="🎒 Инвентарь",
            value=f"**{inv_value} ₽** / **{total_items} шт.**\n\u200b",
            inline=False,
        )
        embed.add_field(
            name="🎖️ Почести",
            value=f"**{honors_count}** шт.",
            inline=False,
        )

        embed.set_footer(text=f"ID: {target.id}")

        view = ProfileActionsView(gid, target, honors_count)
        await interaction.response.send_message(embed=embed, view=view)


class InventoryPaginator(discord.ui.View):
    ITEMS_PER_PAGE = 5

    def __init__(self, inventory: List[str], total_value: int, total_items: int,
                 user_id: int, items_data: dict):
        super().__init__(timeout=60)
        self.inventory = inventory
        self.total_value = total_value
        self.total_items = total_items
        self.user_id = user_id
        self.items_data = items_data
        self.current_page = 0
        self.message = None

    def get_page(self, page: int):
        counter = Counter(self.inventory)
        grouped = sorted(counter.items(), key=lambda x: x[0])
        start = page * self.ITEMS_PER_PAGE
        end = start + self.ITEMS_PER_PAGE
        page_items = grouped[start:end]
        max_page = (len(grouped) - 1) // self.ITEMS_PER_PAGE + 1 if grouped else 1

        embed = discord.Embed(
            title="🎒 Инвентарь",
            description=(
                f"Всего предметов: **{self.total_items} шт.**\n"
                f"Общая стоимость: **{self.total_value} ₽**"
            ),
            color=discord.Color.blue(),
        )
        if page_items:
            lines = []
            for item_name, count in page_items:
                desc = self.items_data.get(item_name, {}).get("description", "")
                line = f"**{item_name}** x{count}"
                if desc:
                    line += f"\n*{desc}*"
                lines.append(line)
            embed.add_field(name=f"Страница {page + 1} из {max_page}",
                            value="\n\n".join(lines), inline=False)
        else:
            embed.add_field(name="Страница пуста",
                            value="Нет предметов на этой странице.", inline=False)
        return embed, max_page

    @discord.ui.button(label="◀ Назад", style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Эти кнопки не для вас!", ephemeral=True)
            return
        if self.current_page == 0:
            await interaction.response.send_message("Вы уже на первой странице.", ephemeral=True)
            return
        self.current_page -= 1
        embed, _ = self.get_page(self.current_page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Вперед ▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Эти кнопки не для вас!", ephemeral=True)
            return
        counter = Counter(self.inventory)
        max_page = (len(counter) - 1) // self.ITEMS_PER_PAGE + 1 if counter else 1
        if self.current_page >= max_page - 1:
            await interaction.response.send_message("Вы уже на последней странице.", ephemeral=True)
            return
        self.current_page += 1
        embed, _ = self.get_page(self.current_page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if self.message:
            for child in self.children:
                child.disabled = True
            await self.message.edit(view=self)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot))