import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY")
ADMIN_ID        = int(os.getenv("ADMIN_ID", "0"))   # Твой chat_id — главный

DIGEST_INTERVAL_MIN  = 60   # дайджест раз в час
BREAKING_CHECK_MIN   = 10   # проверка срочных каждые 10 мин
MIN_ARTICLES_SOLO    = 3    # минимум статей чтобы категория шла отдельным сообщением

# Дедупликация похожих заголовков внутри одной категории (см. aggregator._dedupe_articles).
# 0.72 подобрано эмпирически: ловит "Х произошло" / "Х: подробности" с разных сайтов,
# не схлопывает разные события с общими словами.
DEDUPE_TITLE_SIMILARITY = 0.72

# Сколько ссылок на первоисточники добавлять под каждым дайджест-сообщением
DIGEST_LINKS_LIMIT = 6

# Источник считается "проблемным" в /sources, если подряд столько раз не отдал
# ни одной новой статьи (не обязательно ошибка — бывает и пусто, но так проще
# заметить реально сдохший RSS)
SOURCE_FAIL_ALERT_THRESHOLD = 20

# Тихий режим: не отправлять ничего с QUIET_START до QUIET_END (по местному времени)
BOT_TIMEZONE  = "Europe/Kyiv"
QUIET_START   = 0   # 00:00 — начало тишины
QUIET_END     = 7   # 07:00 — конец тишины (статьи копятся, в 7 утра уходит большой дайджест)

CATEGORY_HASHTAGS = {
    "🌍 МИР":        "#МИР #Новости #Мировые",
    "🇺🇦 УКРАИНА":   "#Украина #Война #ЗСУ #Ukraine",
    "🇪🇺 ЕВРОПА":    "#Европа #ЕС #Политика #EU",
    "🇺🇸 США":       "#США #Политика #US",
    "💻 ТЕХНОЛОГИИ": "#Технологии #AI #Tech #Инновации",
    "🚗 АВТО":       "#Авто #Машины #EV #Электрокары",
    "💰 ФИНАНСЫ":    "#Финансы #Рынки #Экономика",
    "🏙️ КОНОТОП":   "#Конотоп #Сумщина #УкраинаЖивет",
}

BREAKING_KEYWORDS = [
    "breaking", "urgent", "alert", "explosion", "killed", "attack",
    "nuclear", "earthquake", "crash", "dead", "ceasefire", "strike",
    "missile", "bomb", "war", "invasion", "crisis", "emergency",
    "срочно", "взрыв", "атака", "ракета",
]

# Keywords that are routine vocabulary in some categories (e.g. "crash"/
# "crisis" show up constantly in normal market coverage) — skip the
# keyword match entirely for these categories so they don't trigger a
# false "breaking" hit. Real financial breaking news still gets through
# via the "breaking"/"urgent"/"alert" etc. keywords above, and via the
# AI second-pass confirmation in aggregator._is_breaking / classify_breaking.
BREAKING_EXCLUDE_CATEGORIES = {
    "crash": ["💰 ФИНАНСЫ"],
    "crisis": ["💰 ФИНАНСЫ"],
}

SOURCES = {
    "🌍 МИР": [
        # Reuters закрыл публичные RSS ещё в 2020 — feeds.reuters.com мёртв,
        # заменено на Guardian World (живой и стабильный фид)
        ("Guardian World",  "https://www.theguardian.com/world/rss"),
        ("BBC World",       "http://feeds.bbci.co.uk/news/world/rss.xml"),
        ("AP News",         "https://feeds.apnews.com/rss/world-news"),
        ("Al Jazeera",      "https://www.aljazeera.com/xml/rss/all.xml"),
    ],
    "🇺🇦 УКРАИНА": [
        ("Ukrinform",        "https://www.ukrinform.ua/rss/block-lastnews"),
        ("Kyiv Independent", "https://kyivindependent.com/feed/"),
        ("Ukr Pravda EN",    "https://www.pravda.com.ua/eng/rss/"),
    ],
    "🇪🇺 ЕВРОПА": [
        ("Politico EU",     "https://www.politico.eu/feed/"),
        ("Euronews",        "https://www.euronews.com/rss?format=mrss&level=theme&name=news"),
        ("DW English",      "https://rss.dw.com/rdf/rss-en-all"),
    ],
    "🇺🇸 США": [
        ("AP Politics",     "https://feeds.apnews.com/rss/politics"),
        ("NPR",             "https://feeds.npr.org/1001/rss.xml"),
        ("The Hill",        "https://thehill.com/news/feed/"),
    ],
    "💻 ТЕХНОЛОГИИ": [
        ("TechCrunch",      "https://techcrunch.com/feed/"),
        ("The Verge",       "https://www.theverge.com/rss/index.xml"),
        ("Ars Technica",    "https://feeds.arstechnica.com/arstechnica/index"),
        ("Wired",           "https://www.wired.com/feed/rss"),
    ],
    "🚗 АВТО": [
        ("Electrek",        "https://electrek.co/feed/"),
        ("Motor1",          "https://www.motor1.com/rss/news/all/"),
        ("Car and Driver",  "https://www.caranddriver.com/rss/all.xml.aspx"),
        ("InsideEVs",       "https://insideevs.com/rss/articles/"),
    ],
    "💰 ФИНАНСЫ": [
        # Reuters Business — тот же мёртвый feeds.reuters.com, заменено на MarketWatch
        ("MarketWatch",      "http://feeds.marketwatch.com/marketwatch/topstories/"),
        ("CNBC",             "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ],
    "🏙️ КОНОТОП": [
        ("Інша думка", "https://rsshub.app/telegram/channel/inshadumka"),
    ],
}
