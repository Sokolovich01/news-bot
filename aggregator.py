import asyncio
import re
import logging
import difflib
import feedparser
import aiohttp
from typing import Dict, List

from config import SOURCES, BREAKING_KEYWORDS, BREAKING_EXCLUDE_CATEGORIES, DEDUPE_TITLE_SIMILARITY
from db import is_seen, mark_seen_bulk, record_source_result

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 NewsAggregatorBot/1.0"}


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _parse(content: bytes) -> feedparser.FeedParserDict:
    """Synchronous feedparser call — run in thread"""
    return feedparser.parse(content)


async def _fetch_one(
    session: aiohttp.ClientSession,
    source: str,
    url: str,
    category: str,
) -> List[Dict]:
    try:
        async with session.get(
            url,
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            content = await resp.read()

        feed = await asyncio.to_thread(_parse, content)
        articles = []

        for entry in feed.entries[:20]:
            link = entry.get("link") or entry.get("id", "")
            if not link:
                continue
            if await is_seen(link):
                continue

            desc = _strip_html(
                entry.get("summary") or entry.get("description") or ""
            )[:400]

            articles.append({
                "title":       _strip_html(entry.get("title", "")),
                "url":         link,
                "description": desc,
                "source":      source,
                "category":    category,
            })

        if articles:
            logger.debug(f"[{source}] {len(articles)} new articles")
        await record_source_result(source, category, ok=True, article_count=len(articles))
        return articles

    except Exception as e:
        logger.warning(f"[{source}] fetch error: {e}")
        await record_source_result(source, category, ok=False, error=str(e))
        return []


async def _fetch_all() -> Dict[str, List[Dict]]:
    """Fetch all sources, return new (unseen) articles grouped by category."""
    result: Dict[str, List[Dict]] = {}

    async with aiohttp.ClientSession() as session:
        tasks, categories = [], []
        for cat, feeds in SOURCES.items():
            for name, url in feeds:
                tasks.append(_fetch_one(session, name, url, cat))
                categories.append(cat)

        gathered = await asyncio.gather(*tasks, return_exceptions=True)

    for cat, items in zip(categories, gathered):
        if isinstance(items, list) and items:
            result.setdefault(cat, []).extend(items)

    for cat in result:
        result[cat] = _dedupe_articles(result[cat])

    return result


def _dedupe_articles(articles: List[Dict]) -> List[Dict]:
    """
    Collapse near-duplicate headlines from different sources within the
    same category (e.g. "Zelensky meets Trump" vs "Zelensky, Trump hold
    talks" both covering the same event). Keeps the first-seen article
    of each cluster — order is whatever asyncio.gather returned, so this
    isn't source-priority-aware, just "first wins".
    Similarity is measured with difflib's SequenceMatcher ratio against
    config.DEDUPE_TITLE_SIMILARITY (see config.py for why 0.72).
    """
    kept: List[Dict] = []
    for article in articles:
        title = article["title"].lower()
        if any(
            difflib.SequenceMatcher(None, title, k["title"].lower()).ratio() >= DEDUPE_TITLE_SIMILARITY
            for k in kept
        ):
            continue
        kept.append(article)
    return kept


# ── Public API ──────────────────────────────────────────────────────────────

def _is_breaking(article: Dict) -> bool:
    """
    Stage 1 (cheap): word-boundary keyword match, skipping keywords that
    are routine vocabulary in the article's own category (see
    BREAKING_EXCLUDE_CATEGORIES — e.g. "crash"/"crisis" in ФИНАНСЫ).
    Substring matching previously caused false positives like "crash"
    matching inside unrelated words/phrases; \\b keeps it to whole words.
    This is only a candidate filter — real confirmation happens in
    classify_breaking() (stage 2, AI) inside fetch_breaking_only().
    """
    text = (article["title"] + " " + article["description"]).lower()
    category = article.get("category", "")

    for kw in BREAKING_KEYWORDS:
        if category in BREAKING_EXCLUDE_CATEGORIES.get(kw, []):
            continue
        if re.search(rf"\b{re.escape(kw)}\b", text):
            return True
    return False


async def fetch_for_digest() -> Dict[str, List[Dict]]:
    """
    For the regular digest (see config.DIGEST_INTERVAL_MIN).
    Fetches all unseen articles, marks ALL as seen, returns them grouped.
    """
    articles = await _fetch_all()

    to_mark = [
        (a["url"], a["title"], a["category"])
        for arts in articles.values()
        for a in arts
    ]
    if to_mark:
        await mark_seen_bulk(to_mark)

    return {k: v for k, v in articles.items() if v}


async def fetch_breaking_only() -> List[Dict]:
    """
    For the periodic breaking-news check (see config.BREAKING_CHECK_MIN).
    Fetches unseen articles, runs them through the keyword pre-filter
    (stage 1), then confirms candidates with an AI pass (stage 2, see
    classify_breaking in summarizer.py) before treating them as breaking.
    This catches false positives keywords alone can't (e.g. a headline
    that contains "attack" but is opinion/analysis, not a real event).

    Only CONFIRMED breaking articles are marked as seen. Candidates that
    the AI pass rejects are left unseen, same as non-candidates, so they
    still show up in the next regular digest instead of disappearing.
    """
    articles = await _fetch_all()

    candidates = []
    for cat, arts in articles.items():
        for a in arts:
            if _is_breaking(a):
                candidates.append(a)

    breaking = []
    if candidates:
        from summarizer import classify_breaking
        try:
            confirmed = await classify_breaking(candidates)
        except Exception as e:
            logger.error(f"classify_breaking failed, falling back to keyword match: {e}")
            confirmed = [True] * len(candidates)
        breaking = [a for a, ok in zip(candidates, confirmed) if ok]

    to_mark = [(a["url"], a["title"], a["category"]) for a in breaking]
    if to_mark:
        await mark_seen_bulk(to_mark)

    return breaking


async def fetch_and_mark_all_silent() -> int:
    """
    First-run init: mark everything currently in feeds as seen
    WITHOUT sending a digest.
    Returns count of articles marked.
    """
    articles = await _fetch_all()
    to_mark = [
        (a["url"], a["title"], a["category"])
        for arts in articles.values()
        for a in arts
    ]
    if to_mark:
        await mark_seen_bulk(to_mark)
    return len(to_mark)
