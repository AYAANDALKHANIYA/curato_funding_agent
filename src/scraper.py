"""
src/scraper.py
--------------
Fetches articles from RSS feeds and HTML scrape sources.
Filters articles published within the last 24 hours and containing funding keywords.
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import feedparser
import requests
from bs4 import BeautifulSoup

from config.sources import RSS_SOURCES, SCRAPE_SOURCES, FUNDING_KEYWORDS

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; FundingAgent/1.0)"
REQUEST_TIMEOUT = 15
MAX_ARTICLES_PER_SCRAPE = 20

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_within_24h(dt: datetime) -> bool:
    """Return True if *dt* falls within the last 24 hours."""
    if dt is None:
        return False
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        # Treat naive datetimes as UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return now - timedelta(hours=24) <= dt <= now


def _parse_date(date_str: str):
    """
    Try several common date formats and return a timezone-aware datetime, or None.
    Order tried:
      1. RFC 2822 (used in RSS)
      2. ISO 8601
      3. '%Y-%m-%d %H:%M:%S'
      4. '%Y-%m-%d'
      5. '%B %d, %Y'  (e.g. 'June 10, 2025')
      6. '%b %d, %Y'  (e.g. 'Jun 10, 2025')
    """
    if not date_str:
        return None

    # Attempt RFC 2822 first (common in RSS pubDate)
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    logger.debug("Could not parse date string: %s", date_str)
    return None


def _is_relevant(title: str, summary: str) -> bool:
    """Return True if title or summary contains at least one FUNDING_KEYWORDS term."""
    combined = (title + " " + summary).lower()
    return any(kw in combined for kw in FUNDING_KEYWORDS)


def _get_article_text(url: str) -> str:
    """
    Fetch full article text from *url*.
    Tries common article body CSS selectors; falls back to <body>.
    Strips nav/footer/aside/script/style noise.
    Returns up to 3000 characters of clean text.
    """
    try:
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Remove noise tags
        for tag in soup.find_all(["nav", "footer", "aside", "script", "style"]):
            tag.decompose()

        selectors = [
            "article",
            ".article-body",
            ".post-content",
            ".entry-content",
            ".story-body",
            "main",
        ]
        for sel in selectors:
            container = soup.select_one(sel)
            if container:
                text = container.get_text(separator=" ", strip=True)
                return text[:3000]

        # Fallback: entire body
        body = soup.find("body")
        if body:
            return body.get_text(separator=" ", strip=True)[:3000]
        return ""

    except Exception as exc:
        logger.warning("Failed to fetch article text from %s: %s", url, exc)
        return ""


# ---------------------------------------------------------------------------
# Public fetch functions
# ---------------------------------------------------------------------------

def fetch_rss(source: dict) -> list:
    """
    Parse an RSS source, filter by date and keywords, fetch full article text.

    Args:
        source: dict with keys {name, url, filter_keywords}

    Returns:
        list of article dicts: {title, url, content, source, published_date}
    """
    results = []
    name = source.get("name", "unknown")
    url = source.get("url", "")

    logger.info("Fetching RSS: %s (%s)", name, url)

    try:
        feed = feedparser.parse(url, agent=USER_AGENT, request_headers={"User-Agent": USER_AGENT})
    except Exception as exc:
        logger.error("RSS parse error for %s: %s", name, exc)
        return []

    if feed.bozo and feed.bozo_exception:
        logger.warning("RSS feed %s had bozo error: %s", name, feed.bozo_exception)

    for entry in feed.entries:
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        link = entry.get("link", "")

        # Date handling
        published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if published_parsed:
            try:
                dt = datetime(*published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                dt = None
        else:
            raw_date = entry.get("published") or entry.get("updated") or ""
            dt = _parse_date(raw_date)

        if not _is_within_24h(dt):
            continue

        if not _is_relevant(title, summary):
            continue

        content = _get_article_text(link) if link else summary
        if not content:
            content = summary

        results.append({
            "title": title,
            "url": link,
            "content": content,
            "source": name,
            "published_date": dt.isoformat() if dt else "",
        })

    logger.info("RSS %s: %d relevant articles found", name, len(results))
    return results


def fetch_scrape(source: dict) -> list:
    """
    Scrape an HTML listing page, extract article links, filter by date/keyword.

    Args:
        source: dict with {name, url, article_selector, title_selector, link_selector, date_selector}

    Returns:
        list of article dicts: {title, url, content, source, published_date}
    """
    results = []
    name = source.get("name", "unknown")
    url = source.get("url", "")
    article_sel = source.get("article_selector", "article")
    title_sel = source.get("title_selector", "h2, h3")
    link_sel = source.get("link_selector", "a")
    date_sel = source.get("date_selector", "time")

    logger.info("Scraping: %s (%s)", name, url)

    try:
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        logger.error("HTTP error scraping %s: %s", name, exc)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    articles = soup.select(article_sel)
    logger.debug("%s: found %d article containers", name, len(articles))

    for article in articles[:MAX_ARTICLES_PER_SCRAPE]:
        # Extract title
        title_tag = article.select_one(title_sel)
        title = title_tag.get_text(strip=True) if title_tag else ""

        # Extract link
        link_tag = article.select_one(link_sel)
        link = ""
        if link_tag:
            href = link_tag.get("href", "")
            if href.startswith("http"):
                link = href
            elif href.startswith("/"):
                from urllib.parse import urlparse
                base = urlparse(url)
                link = f"{base.scheme}://{base.netloc}{href}"

        # Extract date
        date_tag = article.select_one(date_sel)
        raw_date = ""
        if date_tag:
            raw_date = date_tag.get("datetime", "") or date_tag.get_text(strip=True)
        dt = _parse_date(raw_date)

        if not _is_within_24h(dt):
            continue

        # Quick relevance check on title alone (no summary available yet)
        if not _is_relevant(title, ""):
            continue

        content = _get_article_text(link) if link else ""
        if not content:
            continue

        # Second relevance pass on full content
        if not _is_relevant(title, content):
            continue

        results.append({
            "title": title,
            "url": link,
            "content": content,
            "source": name,
            "published_date": dt.isoformat() if dt else "",
        })

    logger.info("Scrape %s: %d relevant articles found", name, len(results))
    return results


def fetch_all_articles() -> list:
    """
    Fetch from all RSS and scrape sources.

    Returns:
        Combined list of article dicts.
    """
    all_articles = []

    for source in RSS_SOURCES:
        try:
            articles = fetch_rss(source)
            all_articles.extend(articles)
        except Exception as exc:
            logger.error("Unexpected error fetching RSS %s: %s", source.get("name"), exc)

    for source in SCRAPE_SOURCES:
        try:
            articles = fetch_scrape(source)
            all_articles.extend(articles)
        except Exception as exc:
            logger.error("Unexpected error scraping %s: %s", source.get("name"), exc)

    logger.info("Total articles fetched: %d", len(all_articles))
    return all_articles
