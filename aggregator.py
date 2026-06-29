import asyncio
import re
import logging
import feedparser
import aiohttp
from typing import Dict, List

from config import SOURCES, BREAKING_KEYWORDS
from db import is_seen, mark_seen_bulk

logger = logging.getLogger(__name__)
HEADERS = {"User-Agent": "Mozilla/5.0 NewsAggregatorBot/1.0"}


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _parse(content: bytes) -> feedparser.FeedParserDict:
    return feedparser.parse(content)


async def _fetch_one(session, source, url, category) -> List[Dict]:
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            content = await resp.read()
        feed = await asyncio.to_thread(_parse, content)
        articles = []
        for entry in feed.entries[:20]:
            link = entry.get("link") or entry.get("id", "")
            if not link or await is_seen(link):
                continue
            desc = _strip_html(entry.get("summary") or entry.get("description") or "")[:400]
            articles.append({
                "title": _strip_html(entry.get("title", "")),
                "url": link,
                "description": desc.strip(),
                "source": source,
                "category": category,
            })
        return articles
    except Exception as e:
        logger.warning(f"[{source}] fetch error: {e}")
        return []


async def _fetch_all() -> Dict[str, List[Dict]]:
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
    return result


def _is_breaking(article: Dict) -> bool:
    text = (article.get("title", "") + " " + article.get("description", "")).lower()
    return any(kw in text for kw in BREAKING_KEYWORDS)


async def fetch_for_digest() -> Dict[str, List[Dict]]:
    articles = await _fetch_all()
    to_mark = [
        (a["url"], a["title"], a["category"])
        for arts in articles.values() for a in arts
    ]
    if to_mark:
        await mark_seen_bulk(to_mark)
    return {k: v for k, v in articles.items() if v}


async def fetch_breaking_only() -> List[Dict]:
    articles = await _fetch_all()
    breaking, to_mark = [], []
    for cat, arts in articles.items():
        for a in arts:
            if _is_breaking(a):
                breaking.append(a)
                to_mark.append((a["url"], a["title"], cat))
    if to_mark:
        await mark_seen_bulk(to_mark)
    return breaking


async def fetch_and_mark_all_silent() -> int:
    articles = await _fetch_all()
    to_mark = [
        (a["url"], a["title"], a["category"])
        for arts in articles.values() for a in arts
    ]
    if to_mark:
        await mark_seen_bulk(to_mark)
    return len(to_mark)
