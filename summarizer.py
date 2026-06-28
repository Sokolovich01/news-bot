import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List

from anthropic import AsyncAnthropic
from config import ANTHROPIC_KEY

logger = logging.getLogger(__name__)
client = AsyncAnthropic(api_key=ANTHROPIC_KEY)


async def create_digest(articles_by_category: Dict[str, List[dict]]) -> str:
    """Build AI digest from articles grouped by category."""
    if not articles_by_category:
        return ""

    # Build article list for the prompt
    lines = []
    total = 0
    for cat, arts in articles_by_category.items():
        lines.append(f"\n== {cat} ==")
        for a in arts[:8]:  # cap per category
            lines.append(f"[{a['source']}] {a['title']}")
            if a["description"]:
                lines.append(f"  → {a['description'][:250]}")
            total += 1

    articles_text = "\n".join(lines)
    now_utc = datetime.now(timezone.utc).strftime("%H:%M UTC")

    prompt = f"""Ты — новостной редактор. Получаешь свежие заголовки из множества источников за последние ~10 минут.

Твоя задача — написать **дайджест на русском языке** по следующим правилам:

1. Оставляй только категории, где есть реальные новости
2. В каждой категории — 2–4 ключевых пункта (1–2 предложения каждый)
3. Если несколько источников пишут об одном и том же → объединяй в один пункт
4. Пиши живо, кратко, по сути — никакой воды
5. Формат каждой категории:
   [эмодзи] **НАЗВАНИЕ КАТЕГОРИИ**
   • Пункт 1
   • Пункт 2
6. Ничего не придумывай — только то, что есть в источниках
7. В самом конце строка: 🕐 {now_utc}

НОВОСТИ:
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


async def create_breaking_summary(breaking: List[dict]) -> str:
    """Short breaking-news alert."""
    if not breaking:
        return ""

    lines = [
        f"[{a['source']}] {a['title']}: {a['description'][:200]}"
        for a in breaking[:5]
    ]
    articles_text = "\n".join(lines)

    prompt = f"""Срочные новости. Напиши ОЧЕНЬ короткий алерт на русском (2–3 предложения максимум).
Только факты. Начни с "🚨 СРОЧНО:"

{articles_text}
"""

    resp = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()
