import discord
from discord.ext import commands
from discord import app_commands
import random
from typing import Optional

from utils import data as db

MIN_BET = 100
MAX_BET = 1_000_000


def _parse_bet(profile: dict, amount: int) -> Optional[str]:
    if amount < MIN_BET:
        return f"❌ Минимальная ставка — **{MIN_BET} ₽**."
    if amount > MAX_BET:
        return f"❌ Максимальная ставка — **{MAX_BET} ₽**."
    if profile.get("balance", 0) < amount:
        return f"❌ Недостаточно средств. У вас **{profile.get('balance', 0)} ₽**."
    return None


class GamesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _check_guild(self, interaction: discord.Interaction) -> Optional[int]:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Команда доступна только на сервере.", ephemeral=True
            )
            return None
        return interaction.guild.id

    @app_commands.command(name="bet", description="Сделать ставку в азартной игре")
    @app_commands.choices(game=[
        app_commands.Choice(name="🎰 Слоты", value="slots"),
        app_commands.Choice(name="🎡 Колесо фортуны", value="wheel"),
        app_commands.Choice(name="🃏 Блэкджек", value="blackjack"),
        app_commands.Choice(name="🪙 Орёл или решка", value="coin"),
    ])
    async def bet(self, interaction: discord.Interaction, game: str, amount: int):
        gid = await self._check_guild(interaction)
        if gid is None:
            return

        profile = db.get_profile(gid, interaction.user.id)
        if profile is None:
            await interaction.response.send_message(
                "❌ Вы ещё не зарегистрированы. Используйте `/reg`.", ephemeral=True
            )
            return

        err = _parse_bet(profile, amount)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return

        if game == "slots":
            await self._play_slots(interaction, gid, profile, amount)
        elif game == "wheel":
            await self._play_wheel(interaction, gid, profile, amount)
        elif game == "blackjack":
            await self._play_blackjack(interaction, gid, profile, amount)
        elif game == "coin":
            await self._play_coin(interaction, gid, profile, amount)

    async def _play_slots(self, interaction, gid, profile, bet):
        symbols = ["🍒", "🍋", "🔔", "⭐", "💎", "🎰"]
        weights = [30, 25, 20, 12, 8, 5]
        reels = random.choices(symbols, weights=weights, k=3)

        multiplier = 0
        if reels[0] == reels[1] == reels[2]:
            multiplier = {"🍒": 3, "🍋": 3, "🔔": 5, "⭐": 10, "💎": 20, "🎰": 50}[reels[0]]
        elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
            multiplier = 1

        total_win = bet * multiplier
        net = total_win - bet
        profile["balance"] = profile.get("balance", 0) + net
        
        db.update_profile(gid, interaction.user.id, profile)

        color = discord.Color.green() if net > 0 else discord.Color.red() if net < 0 else discord.Color.light_gray()
        embed = discord.Embed(title="🎰 Слоты", description=f"**{' | '.join(reels)}**", color=color)
        embed.add_field(name="Ставка", value=f"{bet} ₽", inline=True)
        embed.add_field(name="Множитель", value=f"x{multiplier}", inline=True)
        if net > 0:
            embed.add_field(name="Выигрыш", value=f"+{net} ₽", inline=True)
        elif net < 0:
            embed.add_field(name="Проигрыш", value=f"{net} ₽", inline=True)
        else:
            embed.add_field(name="Результат", value="Возврат ставки", inline=True)
        embed.set_footer(text=f"Баланс: {profile['balance']} ₽")
        await interaction.response.send_message(embed=embed)

    async def _play_wheel(self, interaction, gid, profile, bet):
        segments = [
            ("❌ Банкрот", 0), ("💀 Проигрыш", 0), ("🟡 x0.5", 0.5),
            ("⚪ x1", 1), ("🟢 x1.5", 1.5), ("🔵 x2", 2),
            ("🟣 x3", 3), ("🟡 x5", 5), ("🌟 x10", 10),
        ]
        weights = [5, 10, 20, 25, 15, 10, 8, 5, 2]
        label, multiplier = random.choices(segments, weights=weights, k=1)[0]

        total_win = int(bet * multiplier)
        net = total_win - bet
        profile["balance"] = profile.get("balance", 0) + net
        
        db.update_profile(gid, interaction.user.id, profile)

        color = discord.Color.green() if net > 0 else discord.Color.red() if net < 0 else discord.Color.light_gray()
        embed = discord.Embed(title="🎡 Колесо фортуны", description=f"Выпало: **{label}**", color=color)
        embed.add_field(name="Ставка", value=f"{bet} ₽", inline=True)
        if net > 0:
            embed.add_field(name="Выигрыш", value=f"+{net} ₽", inline=True)
        elif net < 0:
            embed.add_field(name="Проигрыш", value=f"{net} ₽", inline=True)
        else:
            embed.add_field(name="Результат", value="Возврат ставки", inline=True)
        embed.set_footer(text=f"Баланс: {profile['balance']} ₽")
        await interaction.response.send_message(embed=embed)

    async def _play_coin(self, interaction, gid, profile, bet):
        coin = random.choice(["Орёл", "Решка"])
        win = coin == "Орёл"

        if win:
            profile["balance"] = profile.get("balance", 0) + bet
            color = discord.Color.green()
            outcome = f"🎉 Победа! Выигрыш: **+{bet} ₽**"
            description = f"🪙 Монета подброшена: **{coin}** — вы угадали!"
        else:
            profile["balance"] = profile.get("balance", 0) - bet
            color = discord.Color.red()
            outcome = f"💀 Проигрыш: **-{bet} ₽**"
            description = f"🪙 Монета подброшена: **{coin}** — не повезло."

        db.update_profile(gid, interaction.user.id, profile)

        embed = discord.Embed(title="🪙 Орёл или решка", description=description, color=color)
        embed.add_field(name="Ставка", value=f"{bet} ₽", inline=True)
        embed.add_field(name="Итог", value=outcome, inline=True)
        embed.set_footer(text=f"Баланс: {profile['balance']} ₽  •  Ставка на «Орёл»")
        await interaction.response.send_message(embed=embed)

    async def _play_blackjack(self, interaction, gid, profile, bet):
        profile["balance"] = profile.get("balance", 0) - bet
        db.update_profile(gid, interaction.user.id, profile)
        game = BlackjackGame(interaction.user.id, gid, bet)
        await game.start(interaction)


SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


def draw_card():
    return random.choice(RANKS), random.choice(SUITS)


def card_value(rank: str) -> int:
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 11
    return int(rank)


def hand_value(hand) -> int:
    total = sum(card_value(r) for r, _ in hand)
    aces = sum(1 for r, _ in hand if r == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def format_hand(hand, hide_last=False) -> str:
    if hide_last:
        cards = [f"`{r}{s}`" for r, s in hand[:-1]] + ["🂠"]
    else:
        cards = [f"`{r}{s}`" for r, s in hand]
    return " ".join(cards)


class BlackjackGame(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int, bet: int):
        super().__init__(timeout=90)
        self.user_id = user_id
        self.guild_id = guild_id
        self.bet = bet
        self.player = [draw_card(), draw_card()]
        self.dealer = [draw_card(), draw_card()]
        self.finished = False

    def build_embed(self, reveal=False) -> discord.Embed:
        pv = hand_value(self.player)
        dv = hand_value(self.dealer) if reveal else card_value(self.dealer[0][0])
        embed = discord.Embed(title="🃏 Блэкджек", color=discord.Color.blue())
        embed.add_field(name=f"Ваши карты ({pv})", value=format_hand(self.player), inline=False)
        embed.add_field(
            name=f"Карты дилера ({dv}{'' if reveal else '+'})",
            value=format_hand(self.dealer, hide_last=not reveal),
            inline=False,
        )
        embed.add_field(name="Ставка", value=f"{self.bet} ₽", inline=True)
        return embed

    async def start(self, interaction: discord.Interaction):
        pv = hand_value(self.player)
        dv = hand_value(self.dealer)
        if pv == 21 and dv == 21:
            await self._finish(interaction, "push")
            return
        if pv == 21:
            await self._finish(interaction, "blackjack")
            return
        await interaction.response.send_message(embed=self.build_embed(False), view=self)

    @discord.ui.button(label="Взять карту", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Не ваша игра.", ephemeral=True)
            return
        if self.finished:
            return
        self.player.append(draw_card())
        pv = hand_value(self.player)
        if pv > 21:
            await self._finish(interaction, "bust")
        elif pv == 21:
            await self._finish(interaction, "stand")
        else:
            await interaction.response.edit_message(embed=self.build_embed(False), view=self)

    @discord.ui.button(label="Хватит", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Не ваша игра.", ephemeral=True)
            return
        if self.finished:
            return
        await self._finish(interaction, "stand")

    async def _finish(self, interaction: discord.Interaction, reason: str):
        self.finished = True
        for child in self.children:
            child.disabled = True

        profile = db.get_profile(self.guild_id, self.user_id)
        if profile is None:
            await interaction.response.send_message("❌ Профиль потерян.", ephemeral=True)
            return

        pv = hand_value(self.player)
        bet = self.bet

        if reason == "blackjack":
            win = int(bet * 2.5)
            profile["balance"] = profile.get("balance", 0) + win
            result = f"🌟 **Блэкджек!** Выигрыш: **+{win - bet} ₽**"
            color = discord.Color.gold()
        elif reason == "bust":
            result = f"💥 Перебор ({pv}). Проигрыш: **-{bet} ₽**"
            color = discord.Color.red()
        elif reason == "push":
            profile["balance"] = profile.get("balance", 0) + bet
            result = "🤝 Ничья. Ставка возвращена."
            color = discord.Color.light_gray()
        else:
            while hand_value(self.dealer) < 17:
                self.dealer.append(draw_card())
            dv = hand_value(self.dealer)

            if dv > 21:
                profile["balance"] = profile.get("balance", 0) + bet * 2
                result = f"🎉 Дилер перебрал ({dv})! Выигрыш: **+{bet} ₽**"
                color = discord.Color.green()
            elif pv > dv:
                profile["balance"] = profile.get("balance", 0) + bet * 2
                result = f"🎉 Вы выиграли ({pv} vs {dv})! Выигрыш: **+{bet} ₽**"
                color = discord.Color.green()
            elif pv == dv:
                profile["balance"] = profile.get("balance", 0) + bet
                result = f"🤝 Ничья ({pv} vs {dv}). Ставка возвращена."
                color = discord.Color.light_gray()
            else:
                result = f"💀 Вы проиграли ({pv} vs {dv}). Проигрыш: **-{bet} ₽**"
                color = discord.Color.red()

        db.update_profile(self.guild_id, self.user_id, profile)

        dv_final = hand_value(self.dealer)
        embed = discord.Embed(title="🃏 Блэкджек — итог", description=result, color=color)
        embed.add_field(name=f"Ваши карты ({pv})", value=format_hand(self.player), inline=False)
        embed.add_field(name=f"Карты дилера ({dv_final})", value=format_hand(self.dealer), inline=False)
        embed.set_footer(text=f"Баланс: {profile['balance']} ₽")

        if interaction.message is not None:
            await interaction.response.edit_message(embed=embed, view=self)
        elif interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.send_message(embed=embed, view=self)


async def setup(bot: commands.Bot):
    await bot.add_cog(GamesCog(bot))