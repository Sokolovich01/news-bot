import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY")
ADMIN_ID        = int(os.getenv("ADMIN_ID", "0"))   # Твой chat_id — главный

DIGEST_INTERVAL_MIN  = 7
BREAKING_CHECK_MIN   = 2

# Тихий режим: не отправлять ничего с QUIET_START до QUIET_END (по местному времени)
BOT_TIMEZONE  = "Europe/Kyiv"
QUIET_START   = 0   # 00:00 — начало тишины
QUIET_END     = 7   # 07:00 — конец тишины (статьи копятся, в 7 утра уходит большой дайджест)

BREAKING_KEYWORDS = [
    "breaking", "urgent", "alert", "explosion", "killed", "attack",
    "nuclear", "earthquake", "crash", "dead", "ceasefire", "strike",
    "missile", "bomb", "war", "invasion", "crisis", "emergency",
    "срочно", "взрыв", "атака", "ракета",
]

SOURCES = {
    "🌍 МИР": [
        ("Reuters",         "https://feeds.reuters.com/reuters/worldNews"),
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
        ("Reuters Business","https://feeds.reuters.com/reuters/businessNews"),
        ("CNBC",            "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ],
}
