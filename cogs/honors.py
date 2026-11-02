import discord
from discord.ext import commands
from discord import app_commands
import time
from typing import Optional

from utils import data as db
from utils import levels as lv


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


class HonorsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _check_guild(self, interaction: discord.Interaction) -> Optional[int]:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return None
        return interaction.guild.id

    async def _check_admin(self, interaction: discord.Interaction) -> Optional[int]:
        gid = await self._check_guild(interaction)
        if gid is None:
            return None
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Нужны права администратора.", ephemeral=True)
            return None
        return gid

    async def _get_member(self, guild: discord.Guild, user_id: int):
        member = guild.get_member(user_id)
        if member is not None:
            return member
        try:
            return await guild.fetch_member(user_id)
        except discord.NotFound:
            return None
        except Exception as e:
            print(f"⚠️ fetch_member({user_id}) ошибка: {e}")
            return None

    @app_commands.command(name="honors", description="Показать почести пользователя")
    async def honors(self, interaction: discord.Interaction, user: discord.User = None):
        gid = await self._check_guild(interaction)
        if gid is None:
            return

        target = user or interaction.user
        
        profile = db.get_profile(gid, target.id)
        if profile is None:
            await interaction.response.send_message(
                f"❌ Пользователь **{target.display_name}** не зарегистрирован.", ephemeral=True
            )
            return

        embed = build_honors_embed(target, profile.get("honors", []))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="honor", description="Управление почестями (админ)")
    @app_commands.choices(action=[
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="remove", value="remove"),
    ])
    async def honor(
        self,
        interaction: discord.Interaction,
        action: str,
        user: discord.User,
        name: str,
        description: str = "",
        icon: str = "🏅",
    ):
        gid = await self._check_admin(interaction)
        if gid is None:
            return

        profile = db.get_profile(gid, user.id)
        if profile is None:
            await interaction.response.send_message(
                f"❌ Пользователь **{user.display_name}** не зарегистрирован.", ephemeral=True
            )
            return

        honors = profile.setdefault("honors", [])

        if action == "add":
            if any(h.get("name") == name for h in honors):
                await interaction.response.send_message(
                    f"❌ У пользователя уже есть почесть `{name}`.", ephemeral=True
                )
                return
            honors.append({
                "name": name,
                "description": description,
                "icon": icon,
                "date": int(time.time()),
            })
            db.update_profile(gid, user.id, profile)
            await interaction.response.send_message(
                f"🏅 {user.mention} присвоена почесть **{icon} {name}**."
            )

        elif action == "remove":
            new_honors = [h for h in honors if h.get("name") != name]
            if len(new_honors) == len(honors):
                await interaction.response.send_message(
                    f"❌ У пользователя нет почести `{name}`.", ephemeral=True
                )
                return
            profile["honors"] = new_honors
            db.update_profile(gid, user.id, profile)
            await interaction.response.send_message(
                f"🗑️ У {user.mention} убрана почесть `{name}`."
            )

    @app_commands.command(
        name="season_reset",
        description="Сбросить уровни всех участников. Легендарные получают почесть сезона."
    )
    async def season_reset(self, interaction: discord.Interaction, year: Optional[int] = None):
        gid = await self._check_admin(interaction)
        if gid is None:
            return

        if year is None:
            year = int(time.strftime("%Y"))

        confirm = SeasonConfirmView(interaction.user.id, gid, year, self.bot)
        await interaction.response.send_message(
            f"⚠️ **Внимание!** Вы собираетесь запустить сезон **{year}**.\n\n"
            f"• Уровень **всех** зарегистрированных участников будет сброшен до 0.\n"
            f"• Баланс будет урезан до 30% + начислен бонус.\n"
            f"• Все ранговые роли будут заменены на «☄️ Новобранец».\n"
            f"• Пользователи с рангом **🎴 Легендарный I–X** получат почесть «🏆 Сезон {year}».\n\n"
            f"Продолжить?",
            view=confirm,
            ephemeral=True,
        )


class SeasonConfirmView(discord.ui.View):
    def __init__(self, author_id: int, guild_id: int, year: int, bot: commands.Bot):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.guild_id = guild_id
        self.year = year
        self.bot = bot

    @discord.ui.button(label="✅ Запустить сезон", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Это не ваша кнопка.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        self.stop()

        profiles = db.load_profiles(self.guild_id)
        total = 0
        legendary = 0
        now_ts = int(time.time())

        for user_id_str, profile in profiles.items():
            level = profile.get("level", 0)
            old_balance = profile.get("balance", 0)

            if level >= 1000:
                bonus = 125000
            elif level >= 800:
                bonus = 75000
            elif level >= 200:
                bonus = 40000
            else:
                bonus = 10000

            new_balance = int(old_balance * 0.3) + bonus
            profile["balance"] = new_balance

            if level >= 1000:
                rank_name = lv.get_rank_name(level)
                honors = profile.setdefault("honors", [])
                if not any(h.get("name") == f"Сезон {self.year}" for h in honors):
                    honors.append({
                        "name": f"Сезон {self.year}",
                        "description": rank_name,
                        "icon": "🏆",
                        "date": now_ts,
                    })
                    legendary += 1

            profile["level"] = 0
            profile["daily_streak"] = 0
            profile["last_daily_day"] = 0
            profile["calendar_start"] = 0
            profile["calendar_day"] = 0

            profiles[user_id_str] = profile
            total += 1

        db.save_profiles(self.guild_id, profiles)

        guild = self.bot.get_guild(self.guild_id)
        roles_updated = 0
        if guild is not None:
            for user_id_str in profiles.keys():
                member = guild.get_member(int(user_id_str))
                if member is None:
                    try:
                        member = await guild.fetch_member(int(user_id_str))
                    except Exception:
                        continue
                res = await lv.sync_rank_roles(guild, member, 1000, 0)
                if res is not None:
                    roles_updated += 1

        await interaction.followup.send(
            f"✅ **Сезон {self.year} запущен!**\n\n"
            f"👥 Обработано профилей: **{total}**\n"
            f"🏆 Выдано почестей за легендарный ранг: **{legendary}**\n"
            f"🎭 Роли обновлены у **{roles_updated}** участников.\n\n"
            f"💰 Балансы урезаны до **30%**, начислен бонус за прошлый ранг:\n"
            f"• Легендарные: +125 000 ₽\n"
            f"• Владыка / Нова / Абсолют: +75 000 ₽\n"
            f"• Ветеран и выше: +40 000 ₽\n"
            f"• Остальные: +10 000 ₽\n"
            f"🎒 Предметы и инвентари сохранены.",
            ephemeral=True,
        )

    @discord.ui.button(label="❌ Отмена", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Это не ваша кнопка.", ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(
            content="❌ Сезон отменён. Ничего не изменилось.",
            view=None,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(HonorsCog(bot))