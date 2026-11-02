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
    if delta == 0:
        return current
    if current >= 999:
        return max(0, current + (1 if delta > 0 else -1))
    result = current + delta
    if result > 999:
        return 1000
    return max(0, result)


def _normalize(name: str) -> str:
    """Убирает variation selectors и приводит к нижнему регистру для сравнения."""
    return unicodedata.normalize("NFKC", name).replace("\ufe0f", "").strip().lower()


def _text_part(name: str) -> str:
    """Возвращает часть имени без эмодзи — например, «новобранец»."""
    return _normalize(name.split(" ", 1)[-1])


def _find_rank_role(guild: discord.Guild, target_name: str):
    """Ищет роль по имени с нормализацией и запасным совпадением по тексту."""
    norm_target = _normalize(target_name)
    text_target = _text_part(target_name)

    # 1. Точное совпадение по нормализованному имени
    for role in guild.roles:
        if _normalize(role.name) == norm_target:
            return role

    # 2. Совпадение по текстовой части (на случай разных вариаций эмодзи)
    for role in guild.roles:
        if _text_part(role.name) == text_target:
            print(f"ℹ️ Роль «{target_name}» найдена как «{role.name}» (совпадение по тексту)")
            return role

    return None


def _is_rank_role(role: discord.Role) -> bool:
    """Проверяет, является ли роль одной из ранговых (с нормализацией)."""
    all_names = {_normalize(n) for n in get_all_rank_names()}
    all_texts = {_text_part(n) for n in get_all_rank_names()}
    return _normalize(role.name) in all_names or _text_part(role.name) in all_texts


async def sync_rank_roles(guild: discord.Guild, member: discord.Member,
                          old_level: int, new_level: int):
    print(f"🔧 sync_rank_roles: guild={guild.id}, member={member.id}, "
          f"{old_level}→{new_level}")

    if guild is None or member is None:
        print("⚠️ guild или member = None — выходим")
        return None

    old_rank = get_rank_name(old_level)
    new_rank = get_rank_name(new_level)
    print(f"🔧 Целевой ранг: {new_rank}")

    user_rank_roles = [r for r in member.roles if _is_rank_role(r)]
    print(f"🔧 Ранговые роли пользователя: {[r.name for r in user_rank_roles]}")

    target_role = _find_rank_role(guild, new_rank)
    has_target = target_role is not None and target_role in member.roles

    extra = [r for r in user_rank_roles if not (target_role and r.id == target_role.id)]

    print(f"🔧 target_role = {target_role.name if target_role else 'None'}, "
          f"has_target = {has_target}, extra = {[r.name for r in extra]}")

    if has_target and not extra:
        print("✅ Роли уже в порядке, ничего не меняем")
        return None

    try:
        if extra:
            await member.remove_roles(*extra, reason="Смена ранга")
            print(f"➖ Удалены роли: {[r.name for r in extra]}")

        if not has_target:
            if target_role is None:
                try:
                    target_role = await guild.create_role(
                        name=new_rank, reason="Автосоздание роли ранга"
                    )
                    print(f"🆕 Создана роль: {new_rank}")
                except discord.Forbidden:
                    print(f"❌ Нет прав на создание роли «{new_rank}»")
                    return None
            await member.add_roles(target_role, reason="Смена ранга")
            print(f"➕ Выдана роль: {target_role.name}")

        return (old_rank, new_rank)
    except discord.Forbidden:
        print(
            f"❌ Нет прав на изменение ролей {member.id} на сервере {guild.id}. "
            f"Проверьте право «Управление ролями» у бота и позицию его роли выше ранговых."
        )
        return None
    except Exception as e:
        print(f"❌ Ошибка синхронизации ранга: {type(e).__name__}: {e}")
        return None