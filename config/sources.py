"""
config/sources.py
-----------------
All source configuration: RSS feeds, scrape targets, funding keywords, and score map.
"""

# ---------------------------------------------------------------------------
# RSS Sources
# ---------------------------------------------------------------------------
RSS_SOURCES = [
    {
        "name": "TechCrunch",
        "url": "https://techcrunch.com/feed/",
        "filter_keywords": ["funding", "raises", "seed", "series", "grant", "investment", "venture"],
    },
    {
        "name": "YourStory",
        "url": "https://yourstory.com/feed",
        "filter_keywords": ["funding", "raises", "seed", "series", "grant", "investment", "venture"],
    },
    {
        "name": "Inc42",
        "url": "https://inc42.com/feed/",
        "filter_keywords": ["funding", "raises", "seed", "series", "grant", "investment", "venture"],
    },
    {
        "name": "Entrackr",
        "url": "https://entrackr.com/feed/",
        "filter_keywords": ["funding", "raises", "seed", "series", "grant", "investment", "venture"],
    },
    {
        "name": "StartupNews.fyi",
        "url": "https://startupnews.fyi/feed/",
        "filter_keywords": ["funding", "raises", "seed", "series", "grant", "investment", "venture"],
    },
    {
        "name": "VCCircle",
        "url": "https://www.vccircle.com/feed",
        "filter_keywords": ["funding", "raises", "seed", "series", "grant", "investment", "venture"],
    },
    {
        "name": "Startup India Blog",
        "url": "https://www.startupindia.gov.in/content/sih/en/blogs.feed.rss",
        "filter_keywords": ["grant", "fund", "accelerator", "scheme", "support"],
    },
]

# ---------------------------------------------------------------------------
# Scrape Sources (HTML page scraping)
# ---------------------------------------------------------------------------
SCRAPE_SOURCES = [
    {
        "name": "Entrackr Funding",
        "url": "https://entrackr.com/category/funding/",
        "article_selector": "article",
        "title_selector": "h2, h3",
        "link_selector": "a",
        "date_selector": "time",
    },
    {
        "name": "Inc42 Buzz",
        "url": "https://inc42.com/buzz/",
        "article_selector": "article",
        "title_selector": "h2, h3",
        "link_selector": "a",
        "date_selector": "time",
    },
]

# ---------------------------------------------------------------------------
# Funding Keywords (used to filter relevant articles)
# ---------------------------------------------------------------------------
FUNDING_KEYWORDS = [
    "raises",
    "raised",
    "funding",
    "funded",
    "seed",
    "series a",
    "series b",
    "series c",
    "pre-seed",
    "angel",
    "grant",
    "accelerator",
    "incubator",
    "venture",
    "investment",
    "invested",
    "scale-up",
    "growth round",
    "venture debt",
    "strategic investment",
    "dpiit",
    "startup india",
    "innovation grant",
]

# ---------------------------------------------------------------------------
# Score Map — announcement_type (lowercase) → base score (int or None)
# None means scored dynamically by funding amount via _score_grant()
# ---------------------------------------------------------------------------
SCORE_MAP = {
    "angel investment": 4,
    "pre-seed": 5,
    "seed": 7,
    "series a": 9,
    "series b": 10,
    "series c": 9,
    "growth round": 8,
    "scale-up funding": 8,
    "strategic investment": 7,
    "venture debt": 6,
    "grant": None,
    "accelerator grant": None,
    "innovation grant": None,
}
