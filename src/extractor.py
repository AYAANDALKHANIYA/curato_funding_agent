"""
src/extractor.py
----------------
Uses the Groq API to extract structured lead data from raw article text.
"""

import json
import logging
import os
import re
import time

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Groq configuration
# ---------------------------------------------------------------------------
_GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
if _GROQ_API_KEY:
    _client = Groq(api_key=_GROQ_API_KEY)
else:
    _client = None
    logger.warning("GROQ_API_KEY not set — extraction will return empty results.")

_MODEL = "llama-3.3-70b-versatile"

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------
SYSTEM_CONTEXT = """You are a funding intelligence analyst. Extract structured data from startup funding/grant announcement articles.

Extract ONLY if the article describes a REAL, SPECIFIC funding event — a named company receiving money.

Skip: roundups/lists, opinion pieces, general news without a specific company receiving funding.

Return ONLY valid JSON. No explanation, no markdown, no backticks.

JSON schema:
{
  "is_funding_announcement": true/false,
  "company_name": "string or null",
  "website_url": "string or null",
  "linkedin_url": "string or null",
  "location": "string or null (city, country)",
  "industry": "string or null",
  "announcement_type": "one of: Grant | Accelerator Grant | Innovation Grant | Angel Investment | Pre-Seed | Seed | Series A | Series B | Series C | Growth Round | Scale-Up Funding | Strategic Investment | Venture Debt | null",
  "funding_amount": "string or null (e.g. '$3M', 'Rs 50 Cr', 'undisclosed')",
  "funding_amount_usd": "number or null (approximate USD value)",
  "funding_stage": "string or null",
  "company_stage": "one of: Idea | MVP | Early Revenue | Growth | Scale | Enterprise | null",
  "why_this_lead": "one sentence explaining why this company needs branding/marketing/website/content services right now"
}

If is_funding_announcement is false, return: {"is_funding_announcement": false}

For why_this_lead, be specific — mention their growth stage and implied marketing needs.
Example: "Raised $3M seed round and entering product-market fit stage, making them a strong buyer of brand identity and growth marketing services."
"""


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences like ```json ... ``` or ``` ... ```."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_lead(article: dict):
    """
    Send one article to Groq and extract a structured lead dict.

    Args:
        article: dict with keys {title, url, content, source, published_date}

    Returns:
        Merged lead dict, or None if not a funding announcement / parse failure.
    """
    if _client is None:
        logger.error("Groq client not initialised — skipping extraction.")
        return None

    title = article.get("title", "")
    source = article.get("source", "")
    url = article.get("url", "")
    date = article.get("published_date", "")
    content = article.get("content", "")[:2500]

    prompt = f"""---
Article Title: {title}
Source: {source}
URL: {url}
Published: {date}

Article Content:
{content}
---

Return JSON only."""

    try:
        response = _client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_CONTEXT},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        raw = response.choices[0].message.content
    except Exception as exc:
        logger.error("Groq API error for article '%s': %s", title, exc)
        return None

    cleaned = _strip_markdown_fences(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning(
            "JSON parse error for article '%s': %s\nRaw response: %s",
            title, exc, raw[:500]
        )
        return None

    if not data.get("is_funding_announcement", False):
        return None

    # Merge article metadata into the lead dict
    lead = {
        "company_name": data.get("company_name"),
        "website_url": data.get("website_url"),
        "linkedin_url": data.get("linkedin_url"),
        "location": data.get("location"),
        "industry": data.get("industry"),
        "announcement_type": data.get("announcement_type"),
        "funding_amount": data.get("funding_amount"),
        "funding_amount_usd": data.get("funding_amount_usd"),
        "funding_stage": data.get("funding_stage"),
        "company_stage": data.get("company_stage"),
        "why_this_lead": data.get("why_this_lead"),
        # Metadata from article
        "announcement_date": date,
        "source_url": url,
        "source_name": source,
    }
    return lead


def extract_all_leads(articles: list) -> list:
    """
    Extract structured lead data from all articles using Groq.

    Args:
        articles: list of article dicts from the scraper.

    Returns:
        list of valid lead dicts (non-None, with company_name set).
    """
    leads = []
    total = len(articles)

    if total == 0:
        logger.info("No articles to extract leads from.")
        return []

    logger.info("Extracting leads from %d articles...", total)

    for idx, article in enumerate(articles, start=1):
        title = article.get("title", "(no title)")
        logger.info("[%d/%d] Extracting: %s", idx, total, title[:80])

        lead = extract_lead(article)

        if lead is None:
            logger.debug("Article skipped (not a funding announcement): %s", title[:80])
            continue

        if not lead.get("company_name"):
            logger.debug("Lead skipped (no company name): %s", title[:80])
            continue

        leads.append(lead)
        # Respectful pacing — avoid hammering the API
        time.sleep(1.0)

    logger.info("Extraction complete: %d leads extracted from %d articles.", len(leads), total)
    return leads
