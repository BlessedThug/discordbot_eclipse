import discord
from discord.ext import commands
from discord import app_commands
import time
from typing import Optional

from utils import data as db
from utils import levels as lv


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _check(self, interaction: discord.Interaction) -> Optional[int]:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return None
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Нужны права администратора.", ephemeral=True)
            return None
        return interaction.guild.id

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

    # ---------- /money ----------
    @app_commands.command(name="money", description="Управление балансом пользователя")
    @app_commands.choices(action=[
        app_commands.Choice(name="give", value="give"),
        app_commands.Choice(name="take", value="take"),
        app_commands.Choice(name="set", value="set"),
    ])
    async def money(self, interaction: discord.Interaction, action: str, user: discord.User, amount: int):
        gid = await self._check(interaction)
        if gid is None:
            return
        if amount < 0:
            await interaction.response.send_message("❌ Сумма не может быть отрицательной.", ephemeral=True)
            return
        profile = db.get_profile(gid, user.id)
        if profile is None:
            await interaction.response.send_message(
                f"❌ Пользователь **{user.display_name}** не зарегистрирован.", ephemeral=True
            )
            return

        if action == "give":
            profile["balance"] = profile.get("balance", 0) + amount
            db.update_profile(gid, user.id, profile)
            await interaction.response.send_message(f"✅ Выдано **{amount} ₽** пользователю {user.mention}.")
        elif action == "take":
            if profile.get("balance", 0) < amount:
                await interaction.response.send_message(
                    f"❌ Недостаточно средств (баланс: {profile.get('balance', 0)} ₽).", ephemeral=True
                )
                return
            profile["balance"] -= amount
            db.update_profile(gid, user.id, profile)
            await interaction.response.send_message(f"✅ Забрано **{amount} ₽** у {user.mention}.")
        elif action == "set":
            profile["balance"] = amount
            db.update_profile(gid, user.id, profile)
            await interaction.response.send_message(f"✅ Баланс {user.mention} = **{amount} ₽**.")

    # ---------- /item ----------
    @app_commands.command(name="item", description="Управление инвентарём (создание кастомных предметов)")
    @app_commands.choices(action=[
        app_commands.Choice(name="give", value="give"),
        app_commands.Choice(name="take", value="take"),
    ])
    async def item(
        self,
        interaction: discord.Interaction,
        action: str,
        user: discord.User,
        item: str,
        count: int = 1,
        price: Optional[int] = None,
        description: Optional[str] = None,
    ):
        gid = await self._check(interaction)
        if gid is None:
            return
        if count <= 0:
            await interaction.response.send_message("❌ Количество должно быть положительным.", ephemeral=True)
            return

        profile = db.get_profile(gid, user.id)
        if profile is None:
            await interaction.response.send_message(
                f"❌ Пользователь **{user.display_name}** не зарегистрирован.", ephemeral=True
            )
            return

        inventory = profile.get("inventory", [])

        if action == "give":
            items_data = db.load_items(gid)
            if item not in items_data:
                if price is None:
                    await interaction.response.send_message(
                        f"❌ Предмет `{item}` отсутствует в каталоге. Укажите `price`, чтобы создать его.",
                        ephemeral=True,
                    )
                    return
                items_data[item] = {
                    "base_price": price,
                    "type": "custom",
                    "effect": None,
                    "description": description or "Пользовательский предмет",
                }
                db.save_items(gid, items_data)
                note = f"\n🆕 Предмет добавлен в каталог с ценой **{price} ₽**."
            else:
                if price is not None:
                    items_data[item]["base_price"] = price
                    if description:
                        items_data[item]["description"] = description
                    db.save_items(gid, items_data)
                    note = f"\n✏️ Цена предмета обновлена: **{price} ₽**."
                else:
                    note = ""

            inventory.extend([item] * count)
            profile["inventory"] = inventory
            db.update_profile(gid, user.id, profile)
            await interaction.response.send_message(
                f"✅ Выдано **{count}** шт. `{item}` пользователю {user.mention}.{note}"
            )

        elif action == "take":
            existing = inventory.count(item)
            if existing < count:
                await interaction.response.send_message(
                    f"❌ У пользователя только {existing} шт. `{item}`.", ephemeral=True
                )
                return
            for _ in range(count):
                inventory.remove(item)
            profile["inventory"] = inventory
            db.update_profile(gid, user.id, profile)
            await interaction.response.send_message(
                f"✅ Забрано **{count}** шт. `{item}` у {user.mention}."
            )

    # ---------- /item_delete ----------
    @app_commands.command(name="item_delete", description="Удалить предмет из каталога")
    async def item_delete(self, interaction: discord.Interaction, item: str):
        gid = await self._check(interaction)
        if gid is None:
            return

        items_data = db.load_items(gid)
        if item not in items_data:
            await interaction.response.send_message(
                f"❌ Предмета `{item}` нет в каталоге.", ephemeral=True
            )
            return

        profiles = db.load_profiles(gid)
        used_in_profiles = any(item in p.get("inventory", []) for p in profiles.values())
        market = db.load_market(gid)
        used_in_market = any(e["item"] == item for e in market)

        del items_data[item]
        db.save_items(gid, items_data)

        warn = ""
        if used_in_profiles:
            warn += "\n⚠️ Предмет остаётся в инвентарях игроков (цена будет 0)."
        if used_in_market:
            warn += "\n⚠️ Предмет остаётся на рынке."

        await interaction.response.send_message(f"🗑️ Предмет `{item}` удалён из каталога.{warn}")

    # ---------- /lvl ----------
    @app_commands.command(name="lvl", description="Управление уровнем пользователя")
    @app_commands.choices(action=[
        app_commands.Choice(name="give", value="give"),
        app_commands.Choice(name="take", value="take"),
        app_commands.Choice(name="set", value="set"),
    ])
    async def lvl(self, interaction: discord.Interaction, action: str, user: discord.User, level: int):
        gid = await self._check(interaction)
        if gid is None:
            return
        if level < 0:
            await interaction.response.send_message("❌ Уровень не может быть отрицательным.", ephemeral=True)
            return

        profile = db.get_profile(gid, user.id)
        if profile is None:
            await interaction.response.send_message(
                f"❌ Пользователь **{user.display_name}** не зарегистрирован.", ephemeral=True
            )
            return

        current = profile.get("level", 0)
        if action == "give":
            new_level = lv.apply_level_change(current, level)
        elif action == "take":
            new_level = lv.apply_level_change(current, -level)
        else:
            new_level = level

        profile["level"] = new_level
        db.update_profile(gid, user.id, profile)

        member = await self._get_member(interaction.guild, user.id)
        rank_change = None
        if member:
            rank_change = await lv.sync_rank_roles(interaction.guild, member, current, new_level)

        result = f"✅ Уровень {user.mention}: **{current} → {new_level}**."
        if action != "set" and new_level != current + (level if action == "give" else -level):
            result += "\n⚠️ Сработал потолок 999+ — изменение составило только ±1."
        if rank_change:
            result += f"\n🏅 Новый ранг: **{rank_change[1]}**"

        await interaction.response.send_message(result)

    # ---------- /status ----------
    @app_commands.command(name="status", description="Управление статусами пользователя")
    @app_commands.choices(action=[
        app_commands.Choice(name="set", value="set"),
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="remove", value="remove"),
    ])
    async def status(
        self,
        interaction: discord.Interaction,
        action: str,
        user: discord.User,
        name: str,
        priority: int = 0,
        days: int = 0,
    ):
        gid = await self._check(interaction)
        if gid is None:
            return
        if days < 0:
            await interaction.response.send_message("❌ Срок не может быть отрицательным.", ephemeral=True)
            return

        profile = db.get_profile(gid, user.id)
        if profile is None:
            await interaction.response.send_message(
                f"❌ Пользователь **{user.display_name}** не зарегистрирован.", ephemeral=True
            )
            return

        statuses = profile.get("statuses", [])
        now = int(time.time())
        expiry = now + days * 86400 if days > 0 else 0

        if action == "set":
            statuses = [{"name": name, "priority": priority, "expiry": expiry}]
        elif action == "add":
            statuses = [s for s in statuses if s["name"] != name]
            statuses.append({"name": name, "priority": priority, "expiry": expiry})
        elif action == "remove":
            new_statuses = [s for s in statuses if s["name"] != name]
            if len(new_statuses) == len(statuses):
                await interaction.response.send_message(
                    f"❌ У пользователя нет статуса `{name}`.", ephemeral=True
                )
                return
            statuses = new_statuses or [{"name": "Участник", "priority": 0, "expiry": 0}]

        profile["statuses"] = statuses
        db.update_profile(gid, user.id, profile)
        await interaction.response.send_message(f"✅ Статусы {user.mention} обновлены.")

    # ---------- /unreg ----------
    @app_commands.command(name="unreg", description="Удалить пользователя из системы на этом сервере")
    async def unreg(self, interaction: discord.Interaction, user: discord.User):
        gid = await self._check(interaction)
        if gid is None:
            return
        if db.get_profile(gid, user.id) is None:
            await interaction.response.send_message(
                f"❌ Пользователь **{user.display_name}** не зарегистрирован.", ephemeral=True
            )
            return
        db.delete_profile(gid, user.id)
        await interaction.response.send_message(f"✅ {user.mention} удалён из системы этого сервера.")

    # ---------- /sync_ranks ----------
    @app_commands.command(name="sync_ranks", description="Синхронизировать роли рангов у всех пользователей")
    async def sync_ranks(self, interaction: discord.Interaction):
        gid = await self._check(interaction)
        if gid is None:
            return

        await interaction.response.defer(ephemeral=True)
        profiles = db.load_profiles(gid)
        updated = 0
        for user_id_str in profiles.keys():
            member = await self._get_member(interaction.guild, int(user_id_str))
            if not member:
                continue
            level = profiles[user_id_str].get("level", 0)
            res = await lv.sync_rank_roles(interaction.guild, member, level, level)
            if res is not None:
                updated += 1

        await interaction.followup.send(f"✅ Обновлено ролей: **{updated}**.", ephemeral=True)

    # ---------- /shop_pool ----------
    @app_commands.command(name="shop_pool", description="Настроить пул предметов для магазина")
    @app_commands.choices(action=[
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="remove", value="remove"),
        app_commands.Choice(name="list", value="list"),
    ])
    async def shop_pool(
        self,
        interaction: discord.Interaction,
        action: str,
        item: Optional[str] = None,
        min_qty: int = 1,
        max_qty: int = 3,
    ):
        gid = await self._check(interaction)
        if gid is None:
            return

        pool = db.load_shop_pool(gid)

        if action == "list":
            if not pool:
                await interaction.response.send_message("📭 Пул магазина пуст.", ephemeral=True)
                return
            lines = [f"• `{name}` — от {r['min']} до {r['max']} шт." for name, r in pool.items()]
            embed = discord.Embed(
                title="🛒 Пул магазина сервера",
                description="\n".join(lines),
                color=discord.Color.blurple(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not item:
            await interaction.response.send_message("❌ Укажите предмет.", ephemeral=True)
            return

        items_data = db.load_items(gid)

        if action == "add":
            if item not in items_data:
                await interaction.response.send_message(
                    f"❌ Предмета `{item}` нет в каталоге. Добавьте его через `/item give`.",
                    ephemeral=True,
                )
                return
            if min_qty < 1 or max_qty < min_qty:
                await interaction.response.send_message("❌ Проверьте диапазон.", ephemeral=True)
                return
            pool[item] = {"min": min_qty, "max": max_qty}
            db.save_shop_pool(gid, pool)
            await interaction.response.send_message(
                f"✅ `{item}` добавлен в пул: от {min_qty} до {max_qty} шт.", ephemeral=True
            )

        elif action == "remove":
            if item not in pool:
                await interaction.response.send_message(f"❌ Предмета `{item}` нет в пуле.", ephemeral=True)
                return
            del pool[item]
            db.save_shop_pool(gid, pool)
            await interaction.response.send_message(
                f"🗑️ `{item}` убран из пула магазина.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))