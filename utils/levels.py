import discord
import unicodedata

LEVEL_RANKS = [
    (0, "☄️ Новобранец"),
    (20, "🛸 Скиталец"),
    (40, "🧭 Искатель"),
    (70, "🎮 Геймер"),
    (100, "📡 Связной"),
    (150, "⚓ Штурман"),
    (200, "⚔️ Ветеран"),
    (300, "🎲 Везунчик"),
    (450, "🔮 Астролог"),
    (600, "🏛️ Магистр"),
    (700, "🌓 Страж Тени"),
    (800, "🌑 Владыка"),
    (900, "🌟 Нова"),
    (999, "🌌 Абсолют"),
]

LEGENDARY_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]


def get_rank_name(level: int) -> str:
    if level >= 1000:
        idx = min(level - 1000, 9)
        return f"🎴 Легендарный {LEGENDARY_ROMAN[idx]}"
    for threshold, name in reversed(LEVEL_RANKS):
        if level >= threshold:
            return name
    return LEVEL_RANKS[0][1]


def get_all_rank_names() -> list:
    return [name for _, name in LEVEL_RANKS] + [f"🎴 Легендарный {r}" for r in LEGENDARY_ROMAN]


def apply_level_change(current: int, delta: int) -> int:
    """Обычное изменение уровня (для /dc)."""
    if delta == 0:
        return current
    if current >= 999:
        return max(0, current + (1 if delta > 0 else -1))
    result = current + delta
    if result > 999:
        return 1000
    return max(0, result)


def apply_level_change_no_legend(current: int, delta: int) -> int:
    """Изменение уровня без возможности стать легендарным (для /open и бустов)."""
    if delta == 0:
        return current
    if current >= 999:
        return current  # Блокируем любые изменения на легендарном ранге
    result = current + delta
    if result > 999:
        return 999  # Жесткий кап на Абсолюте
    return max(0, result)


def _normalize(name: str) -> str:
    return unicodedata.normalize("NFKC", name).replace("\ufe0f", "").strip().lower()

def _text_part(name: str) -> str:
    return _normalize(name.split(" ", 1)[-1])

def _find_rank_role(guild: discord.Guild, target_name: str):
    norm_target = _normalize(target_name)
    text_target = _text_part(target_name)
    for role in guild.roles:
        if _normalize(role.name) == norm_target:
            return role
    for role in guild.roles:
        if _text_part(role.name) == text_target:
            return role
    return None

def _is_rank_role(role: discord.Role) -> bool:
    all_names = {_normalize(n) for n in get_all_rank_names()}
    all_texts = {_text_part(n) for n in get_all_rank_names()}
    return _normalize(role.name) in all_names or _text_part(role.name) in all_texts

async def sync_rank_roles(guild: discord.Guild, member: discord.Member,
                          old_level: int, new_level: int):
    if guild is None or member is None:
        return None

    old_rank = get_rank_name(old_level)
    new_rank = get_rank_name(new_level)

    user_rank_roles = [r for r in member.roles if _is_rank_role(r)]
    target_role = _find_rank_role(guild, new_rank)
    has_target = target_role is not None and target_role in member.roles
    extra = [r for r in user_rank_roles if not (target_role and r.id == target_role.id)]

    if has_target and not extra:
        return None

    try:
        if extra:
            await member.remove_roles(*extra, reason="Смена ранга")
        if not has_target:
            if target_role is None:
                target_role = await guild.create_role(name=new_rank, reason="Автосоздание роли ранга")
            await member.add_roles(target_role, reason="Смена ранга")
        return (old_rank, new_rank)
    except discord.Forbidden:
        print(f"❌ Нет прав на изменение ролей {member.id}.")
        return None
    except Exception as e:
        print(f"❌ Ошибка синхронизации ранга: {e}")
        return None