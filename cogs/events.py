import discord
from discord.ext import commands
from discord import app_commands
import random
import time
import asyncio
from typing import Optional

from utils import data as db
from utils import levels as lv


def build_giveaway_embed(giveaway: dict) -> discord.Embed:
    ends_at = giveaway.get("ends_at", 0)
    return discord.Embed(
        title="🎉 Розыгрыш",
        description=(
            f"**Приз:** {giveaway.get('prize_name', '?')}\n"
            f"**Победителей:** {giveaway.get('places', 1)}\n"
            f"**Участников:** {len(giveaway.get('participants', []))}\n\n"
            f"⏰ Завершится: <t:{ends_at}:R>"
        ),
        color=discord.Color.gold(),
    )


class GiveawayJoinView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎉 Участвовать",
        style=discord.ButtonStyle.success,
        custom_id="giveaway_join_btn",
    )
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return
        gid = interaction.guild.id
        events = db.load_events(gid)
        giveaway = events.get("giveaway")
        if not giveaway or not giveaway.get("active"):
            await interaction.response.send_message("❌ Розыгрыш уже завершён.", ephemeral=True)
            return
        if time.time() >= giveaway.get("ends_at", 0):
            await interaction.response.send_message("❌ Время розыгрыша истекло.", ephemeral=True)
            return
        if interaction.user.id in giveaway.get("participants", []):
            await interaction.response.send_message("❌ Вы уже участвуете!", ephemeral=True)
            return
        giveaway.setdefault("participants", []).append(interaction.user.id)
        db.save_events(gid, events)
        await interaction.response.send_message(
            f"✅ Вы участвуете! Всего участников: {len(giveaway['participants'])}",
            ephemeral=True,
        )
        try:
            await interaction.message.edit(embed=build_giveaway_embed(giveaway))
        except Exception:
            pass


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    event_group = app_commands.Group(name="event", description="Управление событиями")

    async def cog_load(self):
        self.bot.tree.add_command(self.event_group)
        self.bot.loop.create_task(self._resume_on_start())

    async def cog_unload(self):
        try:
            self.bot.tree.remove_command(self.event_group.name)
        except Exception:
            pass

    async def _resume_on_start(self):
        await self.bot.wait_until_ready()
        self.bot.add_view(GiveawayJoinView())
        
        for gid in db.list_guild_ids():
            events = db.load_events(gid)
            giveaway = events.get("giveaway")
            if giveaway and giveaway.get("active"):
                asyncio.create_task(self._run_giveaway(gid))
                print(f"🔄 Возобновлён розыгрыш на сервере {gid}")

    async def _check_admin(self, interaction: discord.Interaction) -> Optional[int]:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return None
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Нужны права администратора.", ephemeral=True)
            return None
        return interaction.guild.id

    # ---------- /event status (для всех) ----------
    @event_group.command(name="status", description="Показать активные события сервера")
    async def event_status(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return
        gid = interaction.guild.id
        events = db.load_events(gid)
        now = time.time()

        embed = discord.Embed(title="📅 Активные события", color=discord.Color.blurple())

        until = events.get("double_daily_until", 0)
        if until > now:
            embed.add_field(
                name="✨ Двойные награды в `/dc`",
                value=f"Активно до <t:{int(until)}:R>",
                inline=False,
            )
        else:
            embed.add_field(name="✨ Двойные награды в `/dc`", value="*Не активно*", inline=False)

        giveaway = events.get("giveaway")
        if giveaway and giveaway.get("active") and giveaway.get("ends_at", 0) > now:
            embed.add_field(
                name="🎉 Розыгрыш",
                value=(
                    f"**Приз:** {giveaway.get('prize_name', '?')}\n"
                    f"**Победителей:** {giveaway.get('places', 1)}\n"
                    f"**Участников:** {len(giveaway.get('participants', []))}\n"
                    f"Завершится: <t:{int(giveaway['ends_at'])}:R>"
                ),
                inline=False,
            )
        else:
            embed.add_field(name="🎉 Розыгрыш", value="*Не активно*", inline=False)

        await interaction.response.send_message(embed=embed)

    # ---------- /event double_daily ----------
    @event_group.command(
        name="double_daily",
        description="Двойные награды в /dc, отрицательные блокируются"
    )
    async def event_double_daily(self, interaction: discord.Interaction, hours: int = 24):
        gid = await self._check_admin(interaction)
        if gid is None:
            return
        if hours < 1 or hours > 168:
            await interaction.response.send_message(
                "❌ Длительность: от 1 до 168 часов.", ephemeral=True
            )
            return

        events = db.load_events(gid)
        until = int(time.time()) + hours * 3600
        events["double_daily_until"] = until
        db.save_events(gid, events)

        embed = discord.Embed(
            title="✨ Событие запущено!",
            description=(
                f"**Двойные награды в `/dc`** активны до <t:{until}:F> (<t:{until}:R>).\n"
                f"Отрицательные награды в этот период **не засчитываются**."
            ),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)

    # ---------- /event giveaway ----------
    @event_group.command(name="giveaway", description="Запустить розыгрыш")
    @app_commands.choices(prize_type=[
        app_commands.Choice(name="Деньги", value="money"),
        app_commands.Choice(name="Предмет", value="item"),
        app_commands.Choice(name="Уровень", value="level"),
    ])
    async def event_giveaway(
        self,
        interaction: discord.Interaction,
        prize_type: str,
        prize_value: str,
        places: int = 1,
        minutes: int = 60,
    ):
        gid = await self._check_admin(interaction)
        if gid is None:
            return

        events = db.load_events(gid)
        if events.get("giveaway") and events["giveaway"].get("active"):
            await interaction.response.send_message(
                "❌ На сервере уже идёт розыгрыш. Дождитесь его завершения.", ephemeral=True
            )
            return

        if places < 1 or places > 50:
            await interaction.response.send_message(
                "❌ Количество мест: от 1 до 50.", ephemeral=True
            )
            return
        if minutes < 1 or minutes > 10080:
            await interaction.response.send_message(
                "❌ Длительность: от 1 минуты до 7 дней (10080 мин).", ephemeral=True
            )
            return

        items_data = db.load_items(gid)
        if prize_type == "money":
            try:
                amount = int(prize_value)
            except ValueError:
                await interaction.response.send_message("❌ Сумма должна быть числом.", ephemeral=True)
                return
            if amount < 1:
                await interaction.response.send_message("❌ Сумма должна быть положительной.", ephemeral=True)
                return
            prize_name = f"💰 {amount} ₽"
            prize_data = amount
        elif prize_type == "level":
            try:
                lvl_amount = int(prize_value)
            except ValueError:
                await interaction.response.send_message("❌ Уровни должны быть числом.", ephemeral=True)
                return
            if lvl_amount < 1:
                await interaction.response.send_message("❌ Уровни должны быть положительными.", ephemeral=True)
                return
            prize_name = f"📘 +{lvl_amount} уровней"
            prize_data = lvl_amount
        else:  # item
            if prize_value not in items_data:
                await interaction.response.send_message(
                    f"❌ Предмета `{prize_value}` нет в каталоге этого сервера.", ephemeral=True
                )
                return
            prize_name = f"📦 {prize_value}"
            prize_data = prize_value

        ends_at = int(time.time()) + minutes * 60
        giveaway = {
            "active": True,
            "prize_type": prize_type,
            "prize_value": prize_data,
            "prize_name": prize_name,
            "places": places,
            "ends_at": ends_at,
            "participants": [],
            "host_id": interaction.user.id,
            "channel_id": interaction.channel.id,
            "message_id": None,
        }
        events["giveaway"] = giveaway
        db.save_events(gid, events)

        embed = build_giveaway_embed(giveaway)
        await interaction.response.send_message(embed=embed, view=GiveawayJoinView())

        try:
            msg = await interaction.original_response()
            giveaway["message_id"] = msg.id
            db.save_events(gid, events)
        except Exception as e:
            print(f"⚠️ Не удалось сохранить message_id: {e}")

        asyncio.create_task(self._run_giveaway(gid))

    # ---------- Логика завершения розыгрыша ----------
    async def _run_giveaway(self, guild_id: int):
        events = db.load_events(guild_id)
        giveaway = events.get("giveaway")
        if not giveaway or not giveaway.get("active"):
            return

        delay = giveaway.get("ends_at", 0) - time.time()
        if delay > 0:
            await asyncio.sleep(delay)

        events = db.load_events(guild_id)
        giveaway = events.get("giveaway")
        if not giveaway or not giveaway.get("active"):
            return
        if time.time() < giveaway.get("ends_at", 0):
            return

        giveaway["active"] = False
        participants = giveaway.get("participants", [])
        places = giveaway.get("places", 1)
        winners = random.sample(participants, min(places, len(participants))) if participants else []

        prize_type = giveaway.get("prize_type")
        prize_value = giveaway.get("prize_value")

        guild = self.bot.get_guild(guild_id)
        for w_id in winners:
            profile = db.get_profile(guild_id, w_id)
            if not profile:
                continue
            if prize_type == "money":
                profile["balance"] = profile.get("balance", 0) + prize_value
            elif prize_type == "level":
                old = profile.get("level", 0)
                new = lv.apply_level_change(old, prize_value)
                profile["level"] = new
                if guild:
                    member = guild.get_member(w_id)
                    if member:
                        try:
                            await lv.sync_rank_roles(guild, member, old, new)
                        except Exception as e:
                            print(f"⚠️ Роль не выдана при розыгрыше: {e}")
            elif prize_type == "item":
                profile.setdefault("inventory", []).append(prize_value)
            db.update_profile(guild_id, w_id, profile)

        db.save_events(guild_id, events)

        if not guild:
            return
        channel = guild.get_channel(giveaway.get("channel_id"))
        if not channel:
            return
        try:
            message = await channel.fetch_message(giveaway.get("message_id"))
        except Exception:
            return

        winners_str = ", ".join(f"<@{w}>" for w in winners) if winners else "— нет участников —"
        embed = discord.Embed(
            title="🎉 Розыгрыш завершён!",
            description=(
                f"**Приз:** {giveaway.get('prize_name', '?')}\n"
                f"**Победители:** {winners_str}\n"
                f"**Участников было:** {len(participants)}"
            ),
            color=discord.Color.gold(),
        )
        try:
            await message.edit(embed=embed, view=None)
        except Exception as e:
            print(f"⚠️ Не удалось обновить сообщение розыгрыша: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))