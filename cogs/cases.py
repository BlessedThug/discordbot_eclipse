import discord
from discord.ext import commands
from discord import app_commands
import random
import time
from typing import Dict, List, Tuple, Optional

from utils import data as db
from utils import levels as lv

DAILY_COOLDOWN = 12 * 3600

RARITY = {
    "Ужасающая": ("🔶", 0x8B0000),
    "Отрицательная": ("🔸", 0xFF4500),
    "Нейтральная": ("⚪", 0x808080),
    "Обычная": ("🟢", 0x00FF00),
    "Редкая": ("🔵", 0x0080FF),
    "Эпическая": ("🟣", 0x8B00FF),
    "Тайная": ("🔴", 0xFF0000),
    "Легендарная": ("🟡", 0xFFD700),
}

RARITY_WEIGHTS = {
    "Ужасающая": 0.05,
    "Отрицательная": 0.10,
    "Нейтральная": 0.15,
    "Обычная": 0.25,
    "Редкая": 0.20,
    "Эпическая": 0.15,
    "Тайная": 0.07,
    "Легендарная": 0.03,
}

DAILY_ITEMS = {
    "Ужасающая": [
        ("📘Уровень -100", ("level", -100)),
        ("💸Деньги -50 000 ₽", ("money", -50000)),
    ],
    "Отрицательная": [
        ("📘Уровень -10", ("level", -10)),
        ("💸Деньги -10 000 ₽", ("money", -10000)),
        ("📘Уровень -5", ("level", -5)),
        ("📘Уровень -1", ("level", -1)),
    ],
    "Нейтральная": [
        ("Ничего", ("nothing", 0)),
        ("Ничего", ("nothing", 0)),
    ],
    "Обычная": [
        ("📘Уровень +1", ("level", 1)),
        ("📘Уровень +5", ("level", 5)),
        ("💸Деньги +1000 ₽", ("money", 1000)),
        ("💸Деньги +5000 ₽", ("money", 5000)),
    ],
    "Редкая": [
        ("📘Уровень +10", ("level", 10)),
        ("💸Деньги +10 000 ₽", ("money", 10000)),
    ],
    "Эпическая": [
        ("📘Уровень +25", ("level", 25)),
        ("💸Деньги +25 000 ₽", ("money", 25000)),
        ("👑 VIP (3 дня)", ("vip", 3)),
        ("🔑 Ключ от кейса «Ежедневный»", ("item", "🔑 Ключ от кейса «Ежедневный»")),
        ("🔼 Буст уровня +25", ("item", "🔼 Буст уровня +25")),
    ],
    "Тайная": [
        ("📘Уровень +50", ("level", 50)),
        ("💸Деньги +50 000 ₽", ("money", 50000)),
        ("👑 VIP (7 дней)", ("vip", 7)),
        ("🔑 Ключ от кейса «Денежный»", ("item", "🔑 Ключ от кейса «Денежный»")),
    ],
    "Легендарная": [
        ("📘Уровень +100", ("level", 100)),
        ("💸Деньги +100 000 ₽", ("money", 100000)),
        ("👑 VIP (14 дней)", ("vip", 14)),
        ("🔑 Ключ от кейса «Всё или ничего»", ("item", "🔑 Ключ от кейса «Всё или ничего»")),
        ("⏫ Буст уровня +100", ("item", "⏫ Буст уровня +100")),
    ],
}

CASE_ITEMS = {
    "Денежный": {
        "Обычная": [
            ("💸Деньги +500 ₽", ("money", 500)),
            ("💸Деньги +1000 ₽", ("money", 1000)),
        ],
        "Редкая": [
            ("💸Деньги +2500 ₽", ("money", 2500)),
            ("💸Деньги +6700 ₽", ("money", 6700)),
        ],
        "Эпическая": [
            ("💸Деньги +15 000 ₽", ("money", 15000)),
            ("💸Деньги +25 000 ₽", ("money", 25000)),
        ],
        "Тайная": [("💸Деньги +50 000 ₽", ("money", 50000))],
        "Легендарная": [("💸Деньги +100 000 ₽", ("money", 100000))],
    },
    "Всё или ничего": {
        "Нейтральная": [("Ничего", ("nothing", 0)), ("Ничего", ("nothing", 0))],
        "Отрицательная": [("💸Деньги -10 000 ₽", ("money", -10000))],
        "Ужасающая": [("💸Деньги -50 000 ₽", ("money", -50000))],
        "Обычная": [("💸Деньги +5000 ₽", ("money", 5000))],
        "Редкая": [("💸Деньги +20 000 ₽", ("money", 20000))],
        "Эпическая": [("💸Деньги +50 000 ₽", ("money", 50000))],
        "Тайная": [("💸Деньги +150 000 ₽", ("money", 150000))],
        "Легендарная": [("💸Деньги +200 000 ₽", ("money", 500000))],
    },
    "Прайм": {
        "Редкая": [
            ("📘Уровень +25", ("level", 25)),
            ("💸Деньги +30 000 ₽", ("money", 30000)),
        ],
        "Эпическая": [
            ("📘Уровень +30", ("level", 30)),
            ("💸Деньги +55 000 ₽", ("money", 55000)),
        ],
        "Тайная": [
            ("💸Деньги +75 000 ₽", ("money", 75000)),
            ("💸Деньги +80 000 ₽", ("money", 80000)),
        ],
        "Легендарная": [
            ("💸Деньги +100 000 ₽", ("money", 100000)),
            ("💸Деньги +250 000 ₽", ("money", 250000)),
        ],
    },
}

KEY_MAP = {
    "Денежный": "🔑 Ключ от кейса «Денежный»",
    "Всё или ничего": "🔑 Ключ от кейса «Всё или ничего»",
    "Прайм": "🔑 Ключ от кейса «Прайм»",
    "Ежедневный": "🔑 Ключ от кейса «Ежедневный»",
}


class CasesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _check_guild(self, interaction: discord.Interaction) -> Optional[int]:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Команда доступна только на сервере.", ephemeral=True
            )
            return None
        return interaction.guild.id

    def _pick_item_by_rarity(self, items_by_rarity: Dict[str, List[Tuple[str, Tuple[str, int]]]]):
        available = list(items_by_rarity.keys())
        if not available:
            return "Ничего", ("nothing", 0), "Нейтральная"
        weights = [RARITY_WEIGHTS.get(r, 0.0) for r in available]
        total = sum(weights)
        if total == 0:
            rarity = random.choice(available)
        else:
            rarity = random.choices(available, weights=[w / total for w in weights], k=1)[0]
        item_name, effect = random.choice(items_by_rarity[rarity])
        return item_name, effect, rarity

    async def _apply_effect(self, profile: dict, effect, guild, member,
                            multiplier: float = 1.0, skip_negative: bool = False) -> str:
        etype, value = effect

        if skip_negative and isinstance(value, (int, float)) and value < 0:
            return "🚫 Отрицательная награда заблокирована"

        if etype == "money":
            applied = int(value * multiplier) if value > 0 else value
            profile["balance"] = profile.get("balance", 0) + applied
            suffix = f" (x{multiplier:.2f})" if multiplier > 1 and value > 0 else ""
            return f"{'+' if applied >= 0 else ''}{applied} ₽{suffix}"

        if etype == "level":
            delta = int(value * multiplier) if value > 0 else value
            old = profile.get("level", 0)
            new = lv.apply_level_change(old, delta)
            profile["level"] = new
            if guild and member and old != new:
                await lv.sync_rank_roles(guild, member, old, new)
            actual = new - old
            suffix = f" (x{multiplier:.2f})" if multiplier > 1 and value > 0 else ""
            if value > 0 and actual < delta:
                return f"+{actual} уровней (⚠️ потолок 999+){suffix}"
            if value < 0 and old - new < abs(value):
                return f"{actual} уровней (⚠️ потолок 999+){suffix}"
            return f"{'+' if actual >= 0 else ''}{actual} уровней{suffix}"

        if etype == "vip":
            days = int(value * multiplier) if value > 0 else value
            now = int(time.time())
            expiry = now + days * 86400
            statuses = [s for s in profile.get("statuses", []) if s["name"] != "VIP"]
            statuses.append({"name": "VIP", "priority": 10, "expiry": expiry})
            profile["statuses"] = statuses
            suffix = f" (x{multiplier:.2f})" if multiplier > 1 and value > 0 else ""
            return f"VIP на {days} дней{suffix}"

        if etype == "item":
            inventory = profile.setdefault("inventory", [])
            inventory.append(value)
            return "📦 Добавлено в инвентарь"

        if etype == "nothing":
            return "ничего не произошло"
        return ""

    def _format_single(self, case_name: str, item_name: str, rarity: str,
                       effect_desc: str, footer_note: str = "") -> discord.Embed:
        emoji, color = RARITY.get(rarity, ("", 0x808080))
        description = (
            f"Вы открываете кейс **{case_name}**, и вам выпадает:\n\n"
            f"► {item_name}\n\n⋖ {emoji} {rarity} {emoji} ⋗"
        )
        if effect_desc and ("x" in effect_desc or "🚫" in effect_desc or "VIP" in effect_desc):
            description += f"\n\n{effect_desc}"
        if footer_note:
            description += f"\n\n{footer_note}"
        embed = discord.Embed(
            title="●▬▬▬▬ஜ۩۞۩ஜ▬▬▬▬●",
            description=description,
            color=color,
        )
        embed.set_footer(text="●▬▬▬▬ஜ۩۞۩ஜ▬▬▬▬●")
        return embed

    def _format_multi(self, case_name: str, results: list) -> discord.Embed:
        embed = discord.Embed(
            title="●▬▬▬▬ஜ۩۞۩ஜ▬▬▬▬●",
            description=f"Вы открыли **{len(results)}** кейсов **{case_name}**:",
            color=discord.Color.gold(),
        )
        for i, (item_name, rarity, effect_desc) in enumerate(results, start=1):
            emoji, _ = RARITY.get(rarity, ("", 0))
            embed.add_field(
                name=f"Кейс #{i}",
                value=f"**{item_name}**\n⋖ {emoji} {rarity} {emoji} ⋗",
                inline=False,
            )
        embed.set_footer(text="●▬▬▬▬ஜ۩۞۩ஜ▬▬▬▬●")
        return embed

    # ---------- /dc ----------
    @app_commands.command(name="dc", description="Открыть ежедневный кейс (раз в 12 часов бесплатно)")
    async def daily_case(self, interaction: discord.Interaction):
        gid = await self._check_guild(interaction)
        if gid is None:
            return

        profile = db.get_profile(gid, interaction.user.id)
        if profile is None:
            await interaction.response.send_message(
                "❌ Вы ещё не зарегистрированы. Используйте `/reg`.", ephemeral=True
            )
            return

        now = int(time.time())
        remaining = DAILY_COOLDOWN - (now - profile.get("last_daily", 0))
        if remaining > 0:
            inv = profile.get("inventory", [])
            hint = ""
            if KEY_MAP["Ежедневный"] in inv:
                hint = "\n💡 У вас есть ключ — используйте `/open Ежедневный`, чтобы открыть кейс сейчас."
            await interaction.response.send_message(
                f"⏳ Ежедневный кейс ещё не готов. Осталось ждать "
                f"**{int(remaining // 3600)}ч {int((remaining % 3600) // 60)}мин**.{hint}",
                ephemeral=True,
            )
            return

        events = db.load_events(gid)
        is_vip = db.has_active_status(profile, "VIP")
        is_event = events.get("double_daily_until", 0) > now
        base_mult = 2 if (is_vip or is_event) else 1
        skip = is_vip or is_event

        today_day = int(now // 86400)
        last_day = profile.get("last_daily_day", 0)
        streak = profile.get("daily_streak", 0)
        if last_day == today_day:
            pass
        elif last_day == today_day - 1:
            streak += 1
        else:
            streak = 1
        profile["daily_streak"] = streak
        profile["last_daily_day"] = today_day

        streak_bonus = min((streak - 1) * 5, 50)
        streak_mult = 1 + streak_bonus / 100
        total_mult = base_mult * streak_mult

        item_name, effect, rarity = self._pick_item_by_rarity(DAILY_ITEMS)
        member = interaction.guild.get_member(interaction.user.id)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(interaction.user.id)
            except Exception:
                member = None

        effect_desc = await self._apply_effect(
            profile, effect, interaction.guild, member, total_mult, skip
        )
        profile["last_daily"] = now
        db.update_profile(gid, interaction.user.id, profile)

        note_lines = [f"🔥 Стрик: **{streak}** дн. (+{streak_bonus}%)"]
        if total_mult > 1:
            note_lines.append(f"✨ Общий множитель: **x{total_mult:.2f}**")
        note = "\n".join(note_lines)

        embed = self._format_single("Ежедневный", item_name, rarity, effect_desc, note)
        await interaction.response.send_message(embed=embed)

    # ---------- /open ----------
    @app_commands.command(name="open", description="Открыть платный кейс (можно указать количество)")
    @app_commands.choices(case=[
        app_commands.Choice(name="Денежный", value="Денежный"),
        app_commands.Choice(name="Всё или ничего", value="Всё или ничего"),
        app_commands.Choice(name="Прайм", value="Прайм"),
        app_commands.Choice(name="Ежедневный", value="Ежедневный"),
    ])
    async def open_case(self, interaction: discord.Interaction, case: str, count: int = 1):
        gid = await self._check_guild(interaction)
        if gid is None:
            return
        if count < 1 or count > 10:
            await interaction.response.send_message("❌ Количество: от 1 до 10.", ephemeral=True)
            return

        profile = db.get_profile(gid, interaction.user.id)
        if profile is None:
            await interaction.response.send_message(
                "❌ Вы ещё не зарегистрированы. Используйте `/reg`.", ephemeral=True
            )
            return

        inventory = profile.get("inventory", [])
        required_key = KEY_MAP.get(case)
        if not required_key:
            await interaction.response.send_message("❌ Неизвестный кейс.", ephemeral=True)
            return

        have = inventory.count(required_key)
        if have < count:
            await interaction.response.send_message(
                f"❌ Недостаточно ключей для **{case}**. Нужно {count}, есть {have}.",
                ephemeral=True,
            )
            return

        for _ in range(count):
            inventory.remove(required_key)
        profile["inventory"] = inventory

        if case == "Ежедневный":
            profile["last_daily"] = int(time.time())
            pool = DAILY_ITEMS
        else:
            pool = CASE_ITEMS.get(case)
            if not pool:
                await interaction.response.send_message(
                    "❌ Ошибка: нет предметов для этого кейса.", ephemeral=True
                )
                return

        member = interaction.guild.get_member(interaction.user.id)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(interaction.user.id)
            except Exception:
                member = None

        results = []
        for _ in range(count):
            item_name, effect, rarity = self._pick_item_by_rarity(pool)
            effect_desc = await self._apply_effect(profile, effect, interaction.guild, member)
            results.append((item_name, rarity, effect_desc))

        db.update_profile(gid, interaction.user.id, profile)

        if count == 1:
            item_name, rarity, effect_desc = results[0]
            await interaction.response.send_message(
                embed=self._format_single(case, item_name, rarity, effect_desc)
            )
        else:
            await interaction.response.send_message(embed=self._format_multi(case, results))


async def setup(bot: commands.Bot):
    await bot.add_cog(CasesCog(bot))