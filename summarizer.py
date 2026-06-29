import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List

from anthropic import AsyncAnthropic
from config import ANTHROPIC_KEY

logger = logging.getLogger(__name__)
client = AsyncAnthropic(api_key=ANTHROPIC_KEY)


LANG_NAMES = {"ru": "русском", "uk": "українській"}
BREAKING_PREFIX = {"ru": "🚨 СРОЧНО:", "uk": "🚨 ТЕРМІНОВО:"}
DIGEST_HEADER = {"ru": "ДАЙДЖЕСТ", "uk": "ДАЙДЖЕСТ"}


async def create_digest(articles_by_category: Dict[str, List[dict]], lang: str = "ru") -> str:
    """Build AI digest from articles grouped by category."""
    if not articles_by_category:
        return ""

    lines = []
    total = 0
    for cat, arts in articles_by_category.items():
        lines.append(f"\n== {cat} ==")
        for a in arts[:8]:
            lines.append(f"[{a['source']}] {a['title']}")
            if a["description"]:
                lines.append(f"  → {a['description'][:250]}")
            total += 1

    articles_text = "\n".join(lines)
    now_utc = datetime.now(timezone.utc).strftime("%H:%M UTC")
    lang_name = LANG_NAMES.get(lang, "русском")

    prompt = f"""Ти — новинний редактор. Отримуєш свіжі заголовки з багатьох джерел.

Твоє завдання — написати **дайджест {lang_name} мовою** за такими правилами:

1. Залишай лише категорії з реальними новинами
2. У кожній категорії — 2–4 ключових пункти (1–2 речення кожен)
3. Якщо кілька джерел пишуть про одне й те саме → об'єднуй в один пункт
4. Пиши живо, коротко, по суті — без води
5. Формат кожної категорії:
   [емодзі] **НАЗВА КАТЕГОРІЇ**
   • Пункт 1
   • Пункт 2
6. Нічого не вигадуй — лише те, що є в джерелах
7. В самому кінці рядок: 🕐 {now_utc}

НОВИНИ:
{articles_text}
"""

    resp = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    digest = resp.content[0].text.strip()
    header = f"📰 <b>ДАЙДЖЕСТ</b>  ·  {total} статей\n{'─' * 22}\n\n"
    return header + digest


async def create_breaking_summary(breaking: List[dict], lang: str = "ru") -> str:
    """Short breaking-news alert."""
    if not breaking:
        return ""

    lines = [
        f"[{a['source']}] {a['title']}: {a['description'][:200]}"
        for a in breaking[:5]
    ]
    articles_text = "\n".join(lines)
    lang_name = LANG_NAMES.get(lang, "русском")
    prefix = BREAKING_PREFIX.get(lang, "🚨 СРОЧНО:")

    prompt = f"""Термінові новини. Напиши ДУЖЕ короткий алерт {lang_name} мовою (2–3 речення максимум).
Лише факти. Почни з "{prefix}"

{articles_text}
"""

    resp = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()
