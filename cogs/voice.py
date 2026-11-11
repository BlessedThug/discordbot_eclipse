import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

from utils import data as db

TRIGGER_CHANNEL_NAME = "⚙️┃Создать канал"
DEFAULT_SYMBOL = "🔊"
DEFAULT_NAME_FORMAT = "Лобби ({username})"
SEPARATOR = "┃"

class VoiceCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # 1. Пользователь зашел в канал-триггер
        if after.channel and after.channel.name == TRIGGER_CHANNEL_NAME:
            # Создаем новый канал в той же категории
            guild = member.guild
            category = after.channel.category
            
            channel_name = f"{DEFAULT_SYMBOL}{SEPARATOR}{DEFAULT_NAME_FORMAT.format(username=member.display_name)}"
            
            try:
                new_channel = await guild.create_voice_channel(
                    name=channel_name,
                    category=category,
                    reason=f"Временный канал для {member.display_name}"
                )
                
                # Выдаем создателю права на управление каналом
                await new_channel.set_permissions(member, manage_channels=True, move_members=True, mute_members=True)
                
                # Перемещаем пользователя
                await member.move_to(new_channel)
                
                # Сохраняем в БД
                db.add_temp_voice(new_channel.id, guild.id, member.id)
                
            except Exception as e:
                print(f"⚠️ Ошибка при создании канала: {e}")

        # 2. Пользователь покинул временный канал (и канал опустел)
        if before.channel and before.channel != after.channel:
            temp_info = db.get_temp_voice(before.channel.id)
            if temp_info:
                # Если в канале больше никого нет
                if len(before.channel.members) == 0:
                    try:
                        await before.channel.delete(reason="Временный канал опустел")
                        db.delete_temp_voice(before.channel.id)
                    except discord.NotFound:
                        db.delete_temp_voice(before.channel.id)
                    except Exception as e:
                        print(f"⚠️ Ошибка при удалении канала: {e}")

    # ---------- Команда управления ----------
    voice_group = app_commands.Group(name="voice", description="Управление вашим временным голосовым каналом")

    @voice_group.command(name="name", description="Изменить название канала")
    async def voice_name(self, interaction: discord.Interaction, new_name: str):
        await self._update_channel(interaction, name=new_name)

    @voice_group.command(name="symbol", description="Изменить эмодзи канала")
    async def voice_symbol(self, interaction: discord.Interaction, new_symbol: str):
        if len(new_symbol) > 5:
            await interaction.response.send_message("❌ Эмодзи слишком длинное.", ephemeral=True)
            return
        await self._update_channel(interaction, symbol=new_symbol)

    @voice_group.command(name="count", description="Установить лимит участников (0 - без лимита)")
    async def voice_count(self, interaction: discord.Interaction, limit: int):
        if limit < 0 or limit > 99:
            await interaction.response.send_message("❌ Лимит должен быть от 0 до 99.", ephemeral=True)
            return
            
        temp_info = await self._check_owner(interaction)
        if not temp_info:
            return

        channel = interaction.guild.get_channel(temp_info["channel_id"])
        if channel:
            await channel.edit(user_limit=limit)
            db.update_temp_voice(channel.id, max_users=limit)
            await interaction.response.send_message(f"✅ Лимит участников установлен на **{limit}**.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Канал не найден.", ephemeral=True)

    # ---------- Вспомогательные методы ----------
    async def _check_owner(self, interaction: discord.Interaction) -> Optional[dict]:
        """Проверяет, находится ли пользователь в своем временном канале."""
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ Вы должны находиться в своем голосовом канале.", ephemeral=True)
            return None

        channel = interaction.user.voice.channel
        temp_info = db.get_temp_voice(channel.id)

        if not temp_info:
            await interaction.response.send_message("❌ Этот канал не является временным.", ephemeral=True)
            return None

        if temp_info["owner_id"] != interaction.user.id:
            await interaction.response.send_message("❌ Вы не являетесь создателем этого канала.", ephemeral=True)
            return None

        return temp_info

    async def _update_channel(self, interaction: discord.Interaction, name: str = None, symbol: str = None):
        temp_info = await self._check_owner(interaction)
        if not temp_info:
            return

        channel = interaction.guild.get_channel(temp_info["channel_id"])
        if not channel:
            await interaction.response.send_message("❌ Канал не найден.", ephemeral=True)
            return

        # Определяем текущие значения
        current_symbol = temp_info["custom_symbol"] or DEFAULT_SYMBOL
        current_name = temp_info["custom_name"] or DEFAULT_NAME_FORMAT.format(username=interaction.user.display_name)

        if name is not None:
            current_name = name
            db.update_temp_voice(channel.id, custom_name=name)
        if symbol is not None:
            current_symbol = symbol
            db.update_temp_voice(channel.id, custom_symbol=symbol)

        new_channel_name = f"{current_symbol}{SEPARATOR}{current_name}"
        
        try:
            await channel.edit(name=new_channel_name)
            await interaction.response.send_message(f"✅ Название канала изменено на **{new_channel_name}**.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка при изменении канала: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceCog(bot))