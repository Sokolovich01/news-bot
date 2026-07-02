import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List

from anthropic import AsyncAnthropic
from config import ANTHROPIC_KEY, MIN_ARTICLES_SOLO, CATEGORY_HASHTAGS, DIGEST_LINKS_LIMIT

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


def _get_source_links(articles: List[dict], limit: int = DIGEST_LINKS_LIMIT) -> str:
    """
    Builds an HTML "🔗 Источники:" footer with clickable links back to the
    original articles, deduped by URL, capped at `limit` (config.DIGEST_LINKS_LIMIT)
    so a 12-article digest doesn't turn into a wall of links.
    """
    seen_urls = set()
    lines = []
    for a in articles:
        if a["url"] in seen_urls:
            continue
        seen_urls.add(a["url"])
        lines.append(f'<a href="{a["url"]}">{a["source"]}</a>')
        if len(lines) >= limit:
            break
    if not lines:
        return ""
    return "🔗 Источники: " + " · ".join(lines)


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

    links = _get_source_links(articles)
    if links:
        text += f"\n\n{links}"

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


async def classify_breaking(candidates: List[dict]) -> List[bool]:
    """
    Stage 2 of breaking-news detection (see aggregator.fetch_breaking_only).
    `candidates` already passed the keyword pre-filter in aggregator._is_breaking,
    which only rules out substring noise — it can't tell a real ongoing event
    ("missile strike hits city") from an unrelated use of the same word
    ("stock crash", "war of words", historical retrospective, opinion piece).
    This does one batched AI call over all candidates and returns which ones
    are genuinely urgent/breaking, in the same order as the input list.
    """
    if not candidates:
        return []

    lines = [
        f"{i}. [{c['source']}] {c['title']} — {c['description'][:150]}"
        for i, c in enumerate(candidates)
    ]

    prompt = f"""Ти редактор новин. Нижче список заголовків, які пройшли попередній фільтр за ключовими словами (breaking, attack, missile, crash тощо) і МОЖУТЬ бути терміновими новинами.

Визнач, які з них — СПРАВЖНІ термінові/breaking новини: масштабна подія, що сталась ЩОЙНО (атака, вибух, катастрофа, стихійне лихо, різка ескалація війни, смерть відомої особи тощо).

НЕ вважай терміновими: звичайні ринкові/фінансові новини, аналітику, історичні згадки, спекуляції, м'які формулювання ("могло б", "ймовірно"), клікбейт-заголовки без конкретної події.

Заголовки:
{chr(10).join(lines)}

Відповідай ТІЛЬКИ номерами через кому тих заголовків, які є справжніми терміновими новинами (наприклад: 0, 3). Якщо жоден не підходить — відповідай одним словом "none".
"""

    try:
        resp = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip().lower()
    except Exception as e:
        logger.error(f"classify_breaking AI call failed: {e}")
        # Fail open: if the AI check itself is unavailable, trust the
        # keyword filter rather than silently dropping real breaking news.
        return [True] * len(candidates)

    if "none" in text:
        return [False] * len(candidates)

    confirmed = {int(tok) for tok in re.findall(r"\d+", text)}
    return [i in confirmed for i in range(len(candidates))]


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
    text = resp.content[0].text.strip()

    links = _get_source_links(breaking)
    if links:
        text += f"\n\n{links}"

    return text
