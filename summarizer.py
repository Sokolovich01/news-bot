import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List

from anthropic import AsyncAnthropic
from config import ANTHROPIC_KEY, MIN_ARTICLES_SOLO, CATEGORY_HASHTAGS

logger = logging.getLogger(__name__)
client = AsyncAnthropic(api_key=ANTHROPIC_KEY)

LANG_NAMES = {"ru": "русском", "uk": "українській"}
BREAKING_PREFIX = {"ru": "🚨 СРОЧНО:", "uk": "🚨 ТЕРМІНОВО:"}


def _get_hashtags(category_label: str) -> str:
    """Get hashtags for a category. Handles merged labels like 'A · B'."""
    parts = [p.strip() for p in category_label.split("·")]
    tags = []
    seen = set()
    for part in parts:
        for key, val in CATEGORY_HASHTAGS.items():
            if key in part or part in key:
                for tag in val.split():
                    if tag not in seen:
                        tags.append(tag)
                        seen.add(tag)
    return " ".join(tags)


async def _summarize_one(category_label: str, articles: List[dict], lang: str = "ru") -> str:
    lines = []
    for a in articles[:12]:
        lines.append(f"[{a['source']}] {a['title']}")
        if a["description"]:
            lines.append(f"  → {a['description'][:250]}")

    articles_text = "\n".join(lines)
    now_utc = datetime.now(timezone.utc).strftime("%H:%M UTC")
    count = len(articles)
    lang_name = LANG_NAMES.get(lang, "русском")

    prompt = f"""Ти новинний редактор. Нижче свіжі новини на тему: {category_label}

Напиши коротке резюме {lang_name} мовою:
1. Заголовок: "{category_label}" жирним через HTML тег <b>
2. 3–5 ключових пунктів, кожен 1–2 речення
3. Використовуй • для кожного пункту
4. Лише факти з джерел — нічого не вигадуй
5. Коротко і по суті, без води
6. В кінці рядок: 🕐 {now_utc} · {count} статей

Не додавай хештеги — вони додадуться автоматично.

НОВИНИ:
{articles_text}
"""

    resp = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()

    hashtags = _get_hashtags(category_label)
    if hashtags:
        text += f"\n\n{hashtags}"

    return text


async def create_split_digests(
    articles_by_category: Dict[str, List[dict]],
    lang: str = "ru",
) -> List[str]:
    """
    Returns list of messages — one per category (or merged if small).
    Categories with < MIN_ARTICLES_SOLO articles are merged into one message.
    """
    solo: Dict[str, List[dict]] = {}
    small: Dict[str, List[dict]] = {}

    for cat, arts in articles_by_category.items():
        if not arts:
            continue
        if len(arts) >= MIN_ARTICLES_SOLO:
            solo[cat] = arts
        else:
            small[cat] = arts

    tasks = []
    for cat, arts in solo.items():
        tasks.append((cat, asyncio.create_task(_summarize_one(cat, arts, lang))))

    if small:
        merged_arts = []
        merged_parts = []
        for cat, arts in small.items():
            merged_parts.append(cat)
            merged_arts.extend(arts)
        merged_label = " · ".join(merged_parts)
        tasks.append((merged_label, asyncio.create_task(_summarize_one(merged_label, merged_arts, lang))))

    messages = []
    for label, task in tasks:
        try:
            msg = await task
            if msg:
                messages.append(msg)
        except Exception as e:
            logger.error(f"Task error [{label}]: {e}")

    return messages


async def create_breaking_summary(breaking: List[dict], lang: str = "ru") -> str:
    if not breaking:
        return ""

    lines = [
        f"[{a['source']}] {a['title']}: {a['description'][:200]}"
        for a in breaking[:5]
    ]
    lang_name = LANG_NAMES.get(lang, "русском")
    prefix = BREAKING_PREFIX.get(lang, "🚨 СРОЧНО:")

    prompt = f"""Термінові новини. Напиши ДУЖЕ короткий алерт {lang_name} мовою (2–3 речення максимум).
Лише факти. Почни з "{prefix}"

{chr(10).join(lines)}
"""

    resp = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()
