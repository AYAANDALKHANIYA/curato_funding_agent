"""
src/apify.py
------------
Data enrichment: fills in missing website_url and linkedin_url for leads.

Strategy (in order):
  1. If APIFY_API_TOKEN is set, use the Apify Google Search Results Scraper
     actor to search for the company's website and LinkedIn page.
  2. Fallback: scan the source article page for company website links
     and LinkedIn anchors using BeautifulSoup.
"""

import logging
import os
import re
import time
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

APIFY_TOKEN = os.environ.get("APIFY_API_TOKEN", "").strip()
USER_AGENT = "Mozilla/5.0 (compatible; FundingAgent/1.0)"
REQUEST_TIMEOUT = 15

# Apify actor for Google Search scraping
_GOOGLE_SEARCH_ACTOR = "apify/google-search-scraper"


# ---------------------------------------------------------------------------
# Apify Google Search enrichment
# ---------------------------------------------------------------------------

def _apify_google_search(query: str, max_results: int = 3) -> list:
    """
    Run the Apify Google Search Scraper actor synchronously and return
    a list of organic result URLs.

    Returns an empty list on any failure.
    """
    if not APIFY_TOKEN:
        return []

    try:
        from apify_client import ApifyClient
        client = ApifyClient(APIFY_TOKEN)

        run_input = {
            "queries": query,
            "maxPagesPerQuery": 1,
            "resultsPerPage": max_results,
            "languageCode": "en",
            "mobileResults": False,
        }

        logger.debug("Apify search: %s", query)
        run = client.actor(_GOOGLE_SEARCH_ACTOR).call(run_input=run_input)

        urls = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            organic = item.get("organicResults", [])
            for result in organic:
                url = result.get("url", "")
                if url:
                    urls.append(url)
        return urls

    except Exception as exc:
        logger.debug("Apify Google Search failed for query '%s': %s", query, exc)
        return []


def _find_website_via_apify(company_name: str) -> Optional[str]:
    """Search Google for the company's official website via Apify."""
    query = f"{company_name} official website"
    results = _apify_google_search(query, max_results=5)

    # Filter out news sites, social media, and known non-company domains
    skip_domains = {
        "linkedin.com", "twitter.com", "x.com", "facebook.com",
        "instagram.com", "youtube.com", "crunchbase.com",
        "techcrunch.com", "inc42.com", "yourstory.com", "entrackr.com",
        "vccircle.com", "wikipedia.org", "bloomberg.com", "reuters.com",
        "economictimes.com", "livemint.com", "moneycontrol.com",
    }

    for url in results:
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower().replace("www.", "")
            if not any(skip in domain for skip in skip_domains):
                return url
        except Exception:
            continue
    return None


def _find_linkedin_via_apify(company_name: str) -> Optional[str]:
    """Search Google for the company's LinkedIn page via Apify."""
    query = f"{company_name} LinkedIn company page"
    results = _apify_google_search(query, max_results=5)

    # First pass: look specifically for a company page
    for url in results:
        if "linkedin.com/company" in url.lower():
            return url
            
    # Fallback: return any linkedin url (often an employee or un-slashed path)
    for url in results:
        if "linkedin.com" in url.lower():
            return url

    return None


# ---------------------------------------------------------------------------
# Local fallback enrichment (no API needed)
# ---------------------------------------------------------------------------

def _local_extract(source_url: str, company_name: str) -> dict:
    """
    Attempt to extract the company website and LinkedIn URL from the
    source article page by scanning all anchor tags.

    This is a best-effort fallback when Apify is not available.
    """
    result = {"website_url": None, "linkedin_url": None}

    if not source_url:
        return result

    try:
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(source_url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Remove noise
        for tag in soup.find_all(["nav", "footer", "aside", "script", "style"]):
            tag.decompose()

        # Collect all hrefs from the article body
        skip_domains = {
            "techcrunch.com", "inc42.com", "yourstory.com", "entrackr.com",
            "vccircle.com", "twitter.com", "x.com", "facebook.com",
            "instagram.com", "youtube.com", "google.com", "apple.com",
            "play.google.com", "apps.apple.com", "wikipedia.org",
        }

        company_lower = company_name.lower().strip() if company_name else ""

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href.startswith("http"):
                continue

            from urllib.parse import urlparse
            parsed = urlparse(href)
            domain = parsed.netloc.lower().replace("www.", "")

            # LinkedIn company page
            if "linkedin.com/company" in href.lower() and not result["linkedin_url"]:
                result["linkedin_url"] = href

            # Company website: match domain against company name
            if not result["website_url"] and domain:
                if not any(skip in domain for skip in skip_domains):
                    # Simple heuristic: check if domain contains part of company name
                    domain_base = domain.split(".")[0]
                    name_parts = re.split(r"[\s\-_]+", company_lower)
                    if any(part in domain_base for part in name_parts if len(part) > 2):
                        result["website_url"] = f"{parsed.scheme}://{parsed.netloc}"

            if result["website_url"] and result["linkedin_url"]:
                break

    except Exception as exc:
        logger.debug("Local enrichment failed for %s: %s", source_url, exc)

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich_leads_with_apify(leads: List[dict]) -> List[dict]:
    """
    Enrich a list of lead dicts by filling in missing website_url and
    linkedin_url fields.

    Strategy:
      - If APIFY_API_TOKEN is configured, use Apify Google Search Scraper.
      - Otherwise, fall back to local article-page scraping.
      - Leads that already have both fields populated are skipped.

    Args:
        leads: list of lead dicts from the extractor.

    Returns:
        The same list with website_url and linkedin_url populated where possible.
    """
    if not leads:
        return []

    use_apify = bool(APIFY_TOKEN)
    method = "Apify Google Search" if use_apify else "local article scraping"
    logger.info("Enriching %d leads using %s...", len(leads), method)

    enriched = []
    for i, lead in enumerate(leads, start=1):
        lead = dict(lead)  # shallow copy
        company = lead.get("company_name", "") or ""
        source_url = lead.get("source_url", "") or ""

        has_website = bool(lead.get("website_url"))
        has_linkedin = bool(lead.get("linkedin_url"))

        if has_website and has_linkedin:
            logger.debug("[%d] %s — already enriched, skipping.", i, company)
            enriched.append(lead)
            continue

        logger.info("[%d] Enriching: %s", i, company[:60])

        if use_apify and company:
            # Use Apify Google Search
            if not has_website:
                website = _find_website_via_apify(company)
                if website:
                    lead["website_url"] = website
                    logger.info("  -> Website found: %s", website)

            if not has_linkedin:
                linkedin = _find_linkedin_via_apify(company)
                if linkedin:
                    lead["linkedin_url"] = linkedin
                    logger.info("  -> LinkedIn found: %s", linkedin)

            # Rate limiting for Apify
            time.sleep(2.0)

        # Local fallback for any still-missing fields
        if not lead.get("website_url") or not lead.get("linkedin_url"):
            local = _local_extract(source_url, company)
            if local.get("website_url") and not lead.get("website_url"):
                lead["website_url"] = local["website_url"]
                logger.info("  -> Website (local fallback): %s", local["website_url"])
            if local.get("linkedin_url") and not lead.get("linkedin_url"):
                lead["linkedin_url"] = local["linkedin_url"]
                logger.info("  -> LinkedIn (local fallback): %s", local["linkedin_url"])

        enriched.append(lead)

    filled_web = sum(1 for l in enriched if l.get("website_url"))
    filled_li = sum(1 for l in enriched if l.get("linkedin_url"))
    logger.info(
        "Enrichment done: %d/%d have website, %d/%d have LinkedIn.",
        filled_web, len(enriched), filled_li, len(enriched),
    )

    return enriched
