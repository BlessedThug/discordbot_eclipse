import discord
from discord.ext import commands
from discord import app_commands
import random
import time
from typing import Optional

from utils import data as db

SHOP_RESTOCK_INTERVAL = 4 * 3600  # 4 часа
BUYBACK_SLOTS = 2


class MarketCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- Пересоздание магазина ----------
    def _maybe_restock(self, gid: int) -> dict:
        shop = db.load_shop(gid)
        now = int(time.time())

        needs_restock = (
            not shop.get("items")
            or "buyback" not in shop
            or now - shop.get("last_restock", 0) >= SHOP_RESTOCK_INTERVAL
        )
        if not needs_restock:
            return shop

        items_data = db.load_items(gid)
        pool = db.load_shop_pool(gid)
        available = [name for name in pool if name in items_data]

        new_items = []
        if available:
            selected = random.sample(available, min(5, len(available)))
            for name in selected:
                r = pool[name]
                new_items.append({
                    "item": name,
                    "price": items_data[name]["base_price"],
                    "quantity": random.randint(r["min"], r["max"]),
                })

        sellable = [
            name for name, info in items_data.items()
            if info.get("base_price", 0) > 0
        ]
        buyback = []
        if sellable:
            count = min(BUYBACK_SLOTS, len(sellable))
            selected_buyback = random.sample(sellable, count)
            for name in selected_buyback:
                base = items_data[name]["base_price"]
                mult = random.uniform(0.7, 1.5)  # -30% … +50%
                price = max(1, int(base * mult))
                buyback.append({"item": name, "price": price})

        shop = {
            "items": new_items,
            "buyback": buyback,
            "last_restock": now,
        }
        db.save_shop(gid, shop)
        return shop

    # ---------- /gift ----------
    @app_commands.command(name="gift", description="Подарить игроку предмет или сумму денег")
    async def gift(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        amount: Optional[int] = None,
        item: Optional[str] = None
    ):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return
        gid = interaction.guild.id

        if (amount is None) == (item is None):
            await interaction.response.send_message(
                "❌ Укажите что-то одно: `amount` или `item`.", ephemeral=True
            )
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message("❌ Нельзя дарить самому себе.", ephemeral=True)
            return

        sender = db.get_profile(gid, interaction.user.id)
        receiver = db.get_profile(gid, user.id)
        if sender is None:
            await interaction.response.send_message(
                "❌ Вы не зарегистрированы. Используйте `/reg`.", ephemeral=True
            )
            return
        if receiver is None:
            await interaction.response.send_message(
                f"❌ Пользователь **{user.display_name}** не зарегистрирован.", ephemeral=True
            )
            return

        if amount is not None:
            if amount <= 0:
                await interaction.response.send_message("❌ Сумма должна быть положительной.", ephemeral=True)
                return
            if sender.get("balance", 0) < amount:
                await interaction.response.send_message("❌ Недостаточно средств.", ephemeral=True)
                return
            sender["balance"] -= amount
            receiver["balance"] = receiver.get("balance", 0) + amount
            db.update_profile(gid, interaction.user.id, sender)
            db.update_profile(gid, user.id, receiver)
            await interaction.response.send_message(f"✅ Вы подарили {user.mention} **{amount} ₽**!")
        else:
            if item not in sender.get("inventory", []):
                await interaction.response.send_message(
                    f"❌ У вас нет предмета `{item}` в инвентаре.", ephemeral=True
                )
                return
            sender["inventory"].remove(item)
            receiver.setdefault("inventory", []).append(item)
            db.update_profile(gid, interaction.user.id, sender)
            db.update_profile(gid, user.id, receiver)
            await interaction.response.send_message(f"✅ Вы подарили {user.mention} предмет **{item}**!")

    # ---------- /baltop ----------
    @app_commands.command(name="baltop", description="Топ-10 богачей сервера")
    async def baltop(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return
        gid = interaction.guild.id
        profiles = db.load_profiles(gid)
        if not profiles:
            await interaction.response.send_message("Пока никто не зарегистрирован.")
            return

        sorted_users = sorted(profiles.items(), key=lambda x: x[1].get("balance", 0), reverse=True)[:10]
        embed = discord.Embed(title="🏆 Топ богачей", color=discord.Color.gold())
        lines = []
        for i, (user_id, data) in enumerate(sorted_users, start=1):
            try:
                u = await self.bot.fetch_user(int(user_id))
                name = u.display_name
            except Exception:
                name = f"ID {user_id}"
            lines.append(f"{i}. **{name}** — {data.get('balance', 0)} ₽")
        embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed)

    # ---------- /shop ----------
    @app_commands.command(name="shop", description="Магазин: серверный, скупка и рынок игроков")
    async def shop(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return
        self._maybe_restock(interaction.guild.id)
        embed = discord.Embed(title="🏪 Магазин", description="Выберите раздел:", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=ShopMenuView(self))

    # ---------- /sell ----------
    @app_commands.command(name="sell", description="Выставить предмет из инвентаря на продажу")
    async def sell(self, interaction: discord.Interaction, item: str, price: int):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return
        if price <= 0:
            await interaction.response.send_message("❌ Цена должна быть положительной.", ephemeral=True)
            return
        gid = interaction.guild.id
        profile = db.get_profile(gid, interaction.user.id)
        if profile is None:
            await interaction.response.send_message(
                "❌ Вы не зарегистрированы. Используйте `/reg`.", ephemeral=True
            )
            return
        if item not in profile.get("inventory", []):
            await interaction.response.send_message(
                f"❌ У вас нет предмета `{item}` в инвентаре.", ephemeral=True
            )
            return
        profile["inventory"].remove(item)
        db.update_profile(gid, interaction.user.id, profile)

        market = db.load_market(gid)
        market.append({"seller_id": interaction.user.id, "item": item, "price": price})
        db.save_market(gid, market)
        await interaction.response.send_message(
            f"✅ Предмет `{item}` выставлен на продажу за **{price} ₽**."
        )


# ---------- Меню магазина ----------
class ShopMenuView(discord.ui.View):
    def __init__(self, cog: MarketCog):
        super().__init__(timeout=60)
        self.cog = cog

    @discord.ui.button(label="🛒 Магазин сервера", style=discord.ButtonStyle.success)
    async def server_shop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.guild.id
        shop = self.cog._maybe_restock(gid)
        items_data = db.load_items(gid)

        if not shop.get("items") and not any(shop.get("buyback", [])):
            embed = discord.Embed(
                title="🛒 Магазин сервера",
                description="Товаров нет. Зайдите позже.",
                color=discord.Color.green(),
            )
            await interaction.response.edit_message(embed=embed, view=None)
            return

        next_restock = shop["last_restock"] + SHOP_RESTOCK_INTERVAL
        embed = discord.Embed(title="🛒 Магазин сервера", color=discord.Color.green())
        embed.description = f"🕒 Обновление: <t:{next_restock}:R>"

        # --- Продажа ---
        if shop.get("items"):
            shop_lines = []
            for idx, entry in enumerate(shop["items"], start=1):
                name = entry["item"]
                price = entry["price"]
                qty = entry["quantity"]
                desc = items_data.get(name, {}).get("description", "")
                line = f"**{idx}. {name}** — {price} ₽ (в наличии: {qty} шт.)"
                if desc:
                    line += f"\n*{desc}*"
                shop_lines.append(line)
            embed.add_field(
                name="🛍️ Товары",
                value="\n\n".join(shop_lines),
                inline=False,
            )

        # --- Скупка ---
        buyback = shop.get("buyback", [])
        active_buyback = [b for b in buyback if b is not None]
        if active_buyback:
            embed.add_field(name="\u200b", value="\u200b", inline=False) # Разделитель
            buyback_lines = []
            for i, entry in enumerate(active_buyback, start=1):
                name = entry["item"]
                price = entry["price"]
                base = items_data.get(name, {}).get("base_price", 0)
                diff = price - base
                sign = "+" if diff >= 0 else ""
                pct = int(diff / base * 100) if base > 0 else 0
                buyback_lines.append(
                    f"**{i}. {name}** — {price} ₽ ({sign}{pct}% к базовой)"
                )
            embed.add_field(
                name="💰 Скупка (продайте предмет)",
                value="\n\n".join(buyback_lines),
                inline=False,
            )

        embed.set_footer(text="Кнопки магазина — зелёные, скупки — красные")
        view = ServerShopView(self.cog, shop)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="📦 Рынок пользователей", style=discord.ButtonStyle.primary)
    async def user_market_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.guild.id
        market = db.load_market(gid)
        if not market:
            embed = discord.Embed(
                title="📦 Рынок пользователей",
                description="Пока нет товаров на продажу.",
                color=discord.Color.blue(),
            )
            await interaction.response.edit_message(embed=embed, view=None)
            return

        paginator = MarketPaginator(self.cog, gid, market, 0)
        embed, view = await paginator.get_page(0)
        await interaction.response.edit_message(embed=embed, view=view)


# ---------- Магазин сервера: кнопки покупки и скупки ----------
class ServerShopView(discord.ui.View):
    def __init__(self, cog: MarketCog, shop: dict):
        super().__init__(timeout=60)
        self.cog = cog

        for idx, entry in enumerate(shop.get("items", [])):
            if entry["quantity"] > 0:
                self.add_item(ServerBuyButton(cog, idx, entry["item"], entry["price"]))

        for idx, entry in enumerate(shop.get("buyback", [])):
            if entry is not None:
                self.add_item(BuybackButton(cog, idx, entry["item"], entry["price"]))


class ServerBuyButton(discord.ui.Button):
    def __init__(self, cog: MarketCog, index: int, item: str, price: int):
        super().__init__(label=f"Купить {item} за {price} ₽", style=discord.ButtonStyle.success)
        self.cog = cog
        self.index = index
        self.item = item
        self.price = price

    async def callback(self, interaction: discord.Interaction):
        gid = interaction.guild.id
        shop = db.load_shop(gid)
        items = shop.get("items", [])
        if self.index >= len(items):
            await interaction.response.send_message("❌ Товар больше недоступен.", ephemeral=True)
            return
        entry = items[self.index]
        if entry["item"] != self.item or entry["quantity"] <= 0:
            await interaction.response.send_message("❌ Товара больше нет в наличии.", ephemeral=True)
            return

        profile = db.get_profile(gid, interaction.user.id)
        if profile is None:
            await interaction.response.send_message(
                "❌ Вы не зарегистрированы. Используйте `/reg`.", ephemeral=True
            )
            return
        if profile.get("balance", 0) < self.price:
            await interaction.response.send_message(
                f"❌ Недостаточно средств. Нужно {self.price} ₽.", ephemeral=True
            )
            return

        entry["quantity"] -= 1
        db.save_shop(gid, shop)
        profile["balance"] -= self.price
        profile.setdefault("inventory", []).append(self.item)
        db.update_profile(gid, interaction.user.id, profile)
        await interaction.response.send_message(f"✅ Вы купили **{self.item}** за **{self.price} ₽**!")


class BuybackButton(discord.ui.Button):
    def __init__(self, cog: MarketCog, slot_idx: int, item: str, price: int):
        super().__init__(
            label=f"Продать {item} за {price} ₽",
            style=discord.ButtonStyle.danger,
        )
        self.cog = cog
        self.slot_idx = slot_idx
        self.item = item
        self.price = price

    async def callback(self, interaction: discord.Interaction):
        gid = interaction.guild.id
        shop = db.load_shop(gid)
        buyback = shop.get("buyback", [])

        if self.slot_idx >= len(buyback) or buyback[self.slot_idx] is None:
            await interaction.response.send_message(
                "❌ Это предложение скупки уже использовано.", ephemeral=True
            )
            return
        entry = buyback[self.slot_idx]
        if entry["item"] != self.item or entry["price"] != self.price:
            await interaction.response.send_message(
                "❌ Предложение изменилось. Откройте магазин заново.", ephemeral=True
            )
            return

        profile = db.get_profile(gid, interaction.user.id)
        if profile is None:
            await interaction.response.send_message(
                "❌ Вы не зарегистрированы. Используйте `/reg`.", ephemeral=True
            )
            return
        if self.item not in profile.get("inventory", []):
            await interaction.response.send_message(
                f"❌ У вас нет предмета `{self.item}` в инвентаре.", ephemeral=True
            )
            return

        profile["inventory"].remove(self.item)
        profile["balance"] = profile.get("balance", 0) + self.price
        db.update_profile(gid, interaction.user.id, profile)

        buyback[self.slot_idx] = None
        shop["buyback"] = buyback
        db.save_shop(gid, shop)

        await interaction.response.send_message(
            f"✅ Вы продали **{self.item}** за **{self.price} ₽**!\n"
            f"-# Этот слот скупки больше неактивен до следующего обновления.",
            ephemeral=False,
        )


# ---------- Рынок игроков ----------
class MarketPaginator(discord.ui.View):
    ITEMS_PER_PAGE = 5

    def __init__(self, cog: MarketCog, gid: int, market: list, page: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.gid = gid
        self.market = market
        self.current_page = page

    async def get_page(self, page: int):
        start = page * self.ITEMS_PER_PAGE
        end = start + self.ITEMS_PER_PAGE
        page_items = self.market[start:end]
        max_page = (len(self.market) - 1) // self.ITEMS_PER_PAGE + 1 if self.market else 1

        embed = discord.Embed(title="📦 Рынок пользователей", color=discord.Color.blue())
        if not page_items:
            embed.description = "Нет товаров на этой странице."
        else:
            lines = []
            for i, entry in enumerate(page_items, start=start + 1):
                seller_id = entry.get("seller_id")
                try:
                    seller = await self.cog.bot.fetch_user(seller_id)
                    seller_name = seller.display_name
                except Exception:
                    seller_name = f"ID {seller_id}"
                lines.append(f"{i}. **{entry['item']}** — {entry['price']} ₽ (от {seller_name})")
            embed.description = "\n".join(lines)

        view = discord.ui.View(timeout=60)
        if page > 0:
            view.add_item(PreviousMarketButton(self.cog, self.gid, page))
        if page < max_page - 1:
            view.add_item(NextMarketButton(self.cog, self.gid, page))
        view.add_item(RefreshMarketButton(self.cog, self.gid, page))
        for idx, entry in enumerate(page_items, start=start):
            view.add_item(BuyButton(self.cog, self.gid, idx, entry["item"], entry["price"], entry["seller_id"]))
        return embed, view


class PreviousMarketButton(discord.ui.Button):
    def __init__(self, cog: MarketCog, gid: int, page: int):
        super().__init__(label="◀", style=discord.ButtonStyle.primary)
        self.cog, self.gid, self.page = cog, gid, page

    async def callback(self, interaction: discord.Interaction):
        market = db.load_market(self.gid)
        pag = MarketPaginator(self.cog, self.gid, market, self.page - 1)
        embed, view = await pag.get_page(self.page - 1)
        await interaction.response.edit_message(embed=embed, view=view)


class NextMarketButton(discord.ui.Button):
    def __init__(self, cog: MarketCog, gid: int, page: int):
        super().__init__(label="▶", style=discord.ButtonStyle.primary)
        self.cog, self.gid, self.page = cog, gid, page

    async def callback(self, interaction: discord.Interaction):
        market = db.load_market(self.gid)
        pag = MarketPaginator(self.cog, self.gid, market, self.page + 1)
        embed, view = await pag.get_page(self.page + 1)
        await interaction.response.edit_message(embed=embed, view=view)


class RefreshMarketButton(discord.ui.Button):
    def __init__(self, cog: MarketCog, gid: int, page: int):
        super().__init__(label="🔄", style=discord.ButtonStyle.secondary)
        self.cog, self.gid, self.page = cog, gid, page

    async def callback(self, interaction: discord.Interaction):
        market = db.load_market(self.gid)
        pag = MarketPaginator(self.cog, self.gid, market, self.page)
        embed, view = await pag.get_page(self.page)
        await interaction.response.edit_message(embed=embed, view=view)


class BuyButton(discord.ui.Button):
    def __init__(self, cog: MarketCog, gid: int, index: int, item: str, price: int, seller_id: int):
        super().__init__(label=f"Купить {item} за {price} ₽", style=discord.ButtonStyle.success)
        self.cog, self.gid, self.index = cog, gid, index
        self.item, self.price, self.seller_id = item, price, seller_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id == self.seller_id:
            await interaction.response.send_message("❌ Нельзя купить свой товар.", ephemeral=True)
            return

        market = db.load_market(self.gid)
        found = None
        for i, entry in enumerate(market):
            if (entry["item"] == self.item and entry["seller_id"] == self.seller_id
                    and entry["price"] == self.price):
                found = i
                break
        if found is None:
            await interaction.response.send_message("❌ Товара уже нет на рынке.", ephemeral=True)
            return

        buyer = db.get_profile(self.gid, interaction.user.id)
        if buyer is None:
            await interaction.response.send_message(
                "❌ Вы не зарегистрированы. Используйте `/reg`.", ephemeral=True
            )
            return
        if buyer.get("balance", 0) < self.price:
            await interaction.response.send_message(
                f"❌ Недостаточно средств. Нужно {self.price} ₽.", ephemeral=True
            )
            return

        seller = db.get_profile(self.gid, self.seller_id)
        if seller is None:
            await interaction.response.send_message("❌ Продавец больше не зарегистрирован.", ephemeral=True)
            return

        buyer["balance"] -= self.price
        buyer.setdefault("inventory", []).append(self.item)
        seller["balance"] = seller.get("balance", 0) + self.price

        del market[found]
        db.save_market(self.gid, market)
        db.update_profile(self.gid, interaction.user.id, buyer)
        db.update_profile(self.gid, self.seller_id, seller)

        await interaction.response.send_message(
            f"✅ Вы купили **{self.item}** за **{self.price} ₽** у <@{self.seller_id}>!"
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(MarketCog(bot))