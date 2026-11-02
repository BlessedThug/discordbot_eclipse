import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

@bot.event
async def on_ready():
    # В памяти сейчас пустое дерево — отправляем пустой список в глобальные команды Discord
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync()
    print("✅ Глобальные команды удалены из Discord")
    await bot.close()

bot.run(TOKEN)