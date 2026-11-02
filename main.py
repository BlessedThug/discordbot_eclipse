import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN is None:
    print("❌ Токен не найден! Проверьте .env")
    exit(1)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

GUILD_ID = 800358504316928080  # ваш сервер

# ----- Команда /ping (тест) -----
@bot.tree.command(name='ping', description='Проверка статуса бота')
async def ping(interaction: discord.Interaction):
    allowed_channel = "┇🔧тестовый-сервер"
    if interaction.channel.name != allowed_channel:
        await interaction.response.send_message(
            f"❌ Команда доступна только в канале `{allowed_channel}`.",
            ephemeral=True
        )
        return
    await interaction.response.send_message("🏓 Понг! Бот работает.")

# ----- Команда /sync (админ) -----
@bot.tree.command(name='sync', description='Синхронизировать команды на сервере (админ)')
async def sync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        return
    try:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        await interaction.response.send_message(
            f"✅ Синхронизировано **{len(synced)}** команд.", ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

# ----- Событие on_ready -----
@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} успешно запущен!')

    # 1. Загружаем коги
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f'📂 Загружен ког: {filename}')
            except Exception as e:
                print(f'❌ Ошибка загрузки кога {filename}: {e}')

    # 2. Диагностика: что сейчас в дереве команд
    cmds = [c.name for c in bot.tree.get_commands()]
    print(f'📋 Команды в дереве: {cmds}')

    # 3. Копируем глобальные команды на сервер и синхронизируем
    try:
        GUILD_ID = 800358504316928080
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f'🔄 Синхронизировано {len(synced)} локальных команд для сервера {GUILD_ID}')
    except Exception as e:
        print(f'❌ Ошибка синхронизации: {e}')

# ----- Запуск -----
if __name__ == "__main__":
    bot.run(TOKEN)