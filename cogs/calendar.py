import discord
from discord.ext import commands
from discord import app_commands
import time
from typing import Optional

from utils import data as db
from utils import levels as lv

CALENDAR_DAYS = 28

CALENDAR_REWARDS = [
    {"type": "money", "value": 100},
    {"type": "money", "value": 250},
    {"type": "money", "value": 500},
    {"type": "money", "value": 750},
    {"type": "money", "value": 1000},
    {"type": "money", "value": 1500},
    {"type": "item",  "value": "🔑 Ключ от кейса «Ежедневный»"},
    {"type": "money", "value": 2000},
    {"type": "money", "value": 2500},
    {"type": "money", "value": 3000},
    {"type": "money", "value": 3500},
    {"type": "money", "value": 4000},
    {"type": "money", "value": 4500},
    {"type": "item",  "value": "🔼 Буст уровня +25"},
    {"type": "money", "value": 5000},
    {"type": "money", "value": 6000},
    {"type": "money", "value": 7000},
    {"type": "money", "value": 8000},
    {"type": "money", "value": 9000},
    {"type": "money", "value": 10000},
    {"type": "item",  "value": "🔑 Ключ от кейса «Денежный»"},
    {"type": "money", "value": 12000},
    {"type": "money", "value": 14000},
    {"type": "money", "value": 16000},
    {"type": "money", "value": 18000},
    {"type": "money", "value": 20000},
    {"type": "money", "value": 25000},
    {"type": "combo", "value": [("vip", 3), ("money", 50000)]},
]


def _describe_reward(reward: dict) -> str:
    if reward["type"] == "money":
        return f"💸 {reward['value']} ₽"
    if reward["type"] == "item":
        return f"📦 {reward['value']}"
    if reward["type"] == "level":
        return f"📘 +{reward['value']} уровней"
    if reward["type"] == "vip":
        return f"👑 VIP на {reward['value']} дн."
    if reward["type"] == "combo":
        parts = []
        for sub_type, sub_value in reward["value"]:
            if sub_type == "money":
                parts.append(f"💸 {sub_value} ₽")
            elif sub_type == "vip":
                parts.append(f"👑 VIP на {sub_value} дн.")
            elif sub_type == "level":
                parts.append(f"📘 +{sub_value} уровней")
            elif sub_type == "item":
                parts.append(f"📦 {sub_value}")
        return " + ".join(parts)
    return "?"


def _apply_reward(profile: dict, reward: dict) -> str:
    if reward["type"] == "money":
        profile["balance"] = profile.get("balance", 0) + reward["value"]
    elif reward["type"] == "level":
        old = profile.get("level", 0)
        new = lv.apply_level_change(old, reward["value"])
        profile["level"] = new
    elif reward["type"] == "vip":
        now = int(time.time())
        expiry = now + reward["value"] * 86400
        statuses = [s for s in profile.get("statuses", []) if s["name"] != "VIP"]
        statuses.append({"name": "VIP", "priority": 10, "expiry": expiry})
        profile["statuses"] = statuses
    elif reward["type"] == "item":
        profile.setdefault("inventory", []).append(reward["value"])
    elif reward["type"] == "combo":
        for sub_type, sub_value in reward["value"]:
            if sub_type == "money":
                profile["balance"] = profile.get("balance", 0) + sub_value
            elif sub_type == "vip":
                now = int(time.time())
                expiry = now + sub_value * 86400
                statuses = [s for s in profile.get("statuses", []) if s["name"] != "VIP"]
                statuses.append({"name": "VIP", "priority": 10, "expiry": expiry})
                profile["statuses"] = statuses
            elif sub_type == "item":
                profile.setdefault("inventory", []).append(sub_value)
    return _describe_reward(reward)


def _build_calendar_embed(profile: dict, today: int) -> discord.Embed:
    start = profile.get("calendar_start", 0)
    current = profile.get("calendar_day", 0)

    embed = discord.Embed(
        title="📅 Ежедневный календарь",
        description="Заходите каждый день и открывайте новую ячейку!\nПропуск дня сбрасывает цикл.",
        color=discord.Color.blurple(),
    )

    if start == 0:
        embed.add_field(
            name="Прогресс",
            value="Нажмите «Открыть день», чтобы начать цикл.",
            inline=False,
        )
        return embed

    elapsed = today - start
    if elapsed < 0:
        elapsed = 0

    cells = []
    for i in range(CALENDAR_DAYS):
        if i < current:
            cells.append("✅")
        elif i == current and elapsed == current:
            cells.append("🎁")
        else:
            cells.append("⬜")

    rows = ["".join(cells[i:i + 7]) for i in range(0, CALENDAR_DAYS, 7)]
    embed.add_field(name="Сетка", value="\n".join(rows), inline=False)

    if current >= CALENDAR_DAYS:
        embed.add_field(name="Статус", value="🏆 Цикл завершён! Все 28 дней открыты.", inline=False)
    elif elapsed > current:
        embed.add_field(
            name="Статус",
            value="⚠️ Вы пропустили день — цикл будет сброшен при следующем нажатии.",
            inline=False,
        )
    elif elapsed == current:
        nxt = CALENDAR_REWARDS[current]
        embed.add_field(
            name=f"🎁 Доступен день {current + 1}",
            value=_describe_reward(nxt),
            inline=False,
        )
    else:
        next_in = current - elapsed
        embed.add_field(
            name="Статус",
            value=f"Следующий день откроется через {next_in} дн.",
            inline=False,
        )
    return embed


class CalendarView(discord.ui.View):
    def __init__(self, cog, gid: int, user_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.gid = gid
        self.user_id = user_id

    @discord.ui.button(label="🎁 Открыть день", style=discord.ButtonStyle.success)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Это не ваш календарь.", ephemeral=True)
            return
        await self.cog._claim_day(interaction, self.gid, self.user_id)


class CalendarCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _check_guild(self, interaction: discord.Interaction) -> Optional[int]:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return None
        return interaction.guild.id

    @app_commands.command(name="calendar", description="Ежедневный календарь на 28 дней")
    async def calendar(self, interaction: discord.Interaction):
        gid = await self._check_guild(interaction)
        if gid is None:
            return
        
        profile = db.get_profile(gid, interaction.user.id)
        if profile is None:
            await interaction.response.send_message(
                "❌ Вы ещё не зарегистрированы. Используйте `/reg`.", ephemeral=True
            )
            return
        
        today = int(time.time() // 86400)
        embed = _build_calendar_embed(profile, today)
        view = CalendarView(self, gid, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    async def _claim_day(self, interaction: discord.Interaction, gid: int, user_id: int):
        profile = db.get_profile(gid, user_id)
        if profile is None:
            await interaction.response.send_message("❌ Профиль не найден.", ephemeral=True)
            return

        today = int(time.time() // 86400)
        start = profile.get("calendar_start", 0)
        current = profile.get("calendar_day", 0)

        if start == 0:
            start = today
            profile["calendar_start"] = start
            current = 0
            profile["calendar_day"] = 0

        elapsed = today - start

        if elapsed > current:
            profile["calendar_start"] = today
            profile["calendar_day"] = 0
            db.update_profile(gid, user_id, profile)
            embed = _build_calendar_embed(profile, today)
            embed.insert_field_at(
                0, name="⚠️ Цикл сброшен",
                value="Вы пропустили один или несколько дней. Начинаем заново с 1-го дня.",
                inline=False,
            )
            view = CalendarView(self, gid, user_id)
            await interaction.response.edit_message(embed=embed, view=view)
            return

        if current >= CALENDAR_DAYS:
            await interaction.response.send_message(
                "🏆 Все 28 дней уже открыты. Следующий цикл начнётся, когда пройдёт день после завершения.",
                ephemeral=True,
            )
            return

        if elapsed < current:
            await interaction.response.send_message(
                "⏳ Следующий день ещё не наступил. Заходите завтра.", ephemeral=True
            )
            return

        reward = CALENDAR_REWARDS[current]
        desc = _apply_reward(profile, reward)
        profile["calendar_day"] = current + 1
        
        db.update_profile(gid, user_id, profile)

        embed = _build_calendar_embed(profile, today)
        embed.insert_field_at(
            0, name=f"🎉 День {current + 1} открыт!",
            value=f"Награда: {desc}",
            inline=False,
        )
        view = CalendarView(self, gid, user_id)
        await interaction.response.edit_message(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(CalendarCog(bot))