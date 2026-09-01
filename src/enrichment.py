"""
src/enrichment.py
-----------------
Data enrichment: fills in missing website_url and linkedin_url for leads.

Strategy:
  1. If SERPER_API_KEY is set, use Serper.dev to search Google for the 
     company's website and LinkedIn page.
  2. Fallback: scan the source article page for company website links
     and LinkedIn anchors using BeautifulSoup.
"""

import logging
import os
import re
import json
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "").strip()
APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "").strip()
USER_AGENT = "Mozilla/5.0 (compatible; FundingAgent/1.0)"
REQUEST_TIMEOUT = 15

# ---------------------------------------------------------------------------
# Serper.dev Google Search enrichment
# ---------------------------------------------------------------------------

def _serper_search(query: str, num_results: int = 5) -> list:
    """
    Run a Google Search via Serper.dev and return organic result URLs.
    """
    if not SERPER_API_KEY:
        return []

    url = "https://google.serper.dev/search"
    payload = json.dumps({
        "q": query,
        "num": num_results
    })
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }

    try:
        logger.debug("Serper search: %s", query)
        resp = requests.post(url, headers=headers, data=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        urls = []
        for result in data.get("organic", []):
            link = result.get("link", "")
            if link:
                urls.append(link)
        return urls

    except Exception as exc:
        logger.debug("Serper search failed for query '%s': %s", query, exc)
        return []


def _find_website_via_serper(company_name: str) -> Optional[str]:
    """Search Google for the company's official website via Serper."""
    query = f"{company_name} official website"
    results = _serper_search(query, num_results=5)

    # Filter out news sites, social media, and known non-company domains
    skip_domains = {
        "linkedin.com", "twitter.com", "x.com", "facebook.com",
        "instagram.com", "youtube.com", "crunchbase.com",
        "techcrunch.com", "inc42.com", "yourstory.com", "entrackr.com",
        "vccircle.com", "wikipedia.org", "bloomberg.com", "reuters.com",
        "economictimes.com", "livemint.com", "moneycontrol.com", "pitchbook.com",
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


def _find_linkedin_via_serper(company_name: str) -> Optional[str]:
    """Search Google for the company's LinkedIn page via Serper."""
    query = f"{company_name} LinkedIn company page"
    results = _serper_search(query, num_results=5)

    # First pass: look specifically for a company page
    for url in results:
        if "linkedin.com/company" in url.lower():
            return url
            
    # Fallback: return any linkedin url (often an employee or un-slashed path)
    for url in results:
        if "linkedin.com" in url.lower():
            return url

    return None


def _find_person_linkedin_via_serper(person_name: str, company_name: str) -> Optional[str]:
    """Search Google for the person's LinkedIn page via Serper."""
    query = f'site:linkedin.com/in "{person_name}" "{company_name}"'
    results = _serper_search(query, num_results=5)

    for url in results:
        if "linkedin.com/in" in url.lower():
            return url

    return None

# ---------------------------------------------------------------------------
# Local fallback enrichment (no API needed)
# ---------------------------------------------------------------------------

def _local_extract(source_url: str, company_name: str) -> dict:
    """
    Attempt to extract the company website and LinkedIn URL from the
    source article page by scanning all anchor tags.
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
# Apollo.io B2B Enrichment
# ---------------------------------------------------------------------------

def _apollo_find_contacts(domain: str) -> list:
    """
    Use Apollo.io to find specific marketing/executive roles at the given domain.
    Returns a list of dicts: {"name": str, "title": str, "email": str, "linkedin_url": str}
    """
    if not APOLLO_API_KEY or not domain:
        return []

    url = "https://api.apollo.io/api/v1/mixed_people/api_search"
    headers = {
        "Content-Type": "application/json", 
        "Cache-Control": "no-cache",
        "X-Api-Key": APOLLO_API_KEY
    }
    
    # We are looking for marketing roles and the CEO
    payload = {
        "q_organization_domains": domain,
        "person_titles": [
            "cmo", "chief marketing officer", "vp marketing", 
            "vice president of marketing", "director of marketing", 
            "brand manager", "product marketing", "senior brand manager",
            "ceo", "chief executive officer", "founder"
        ],
        "per_page": 5
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        contacts = []
        for p in data.get("people", []):
            name = p.get("name", "")
            if not name and p.get("first_name"):
                name = p.get("first_name")
            
            title = p.get("title", "")
            email = p.get("email", "")
            linkedin = p.get("linkedin_url", "")
            
            # If search didn't return email, unlock via people/match
            if not email and p.get("has_email"):
                match_url = "https://api.apollo.io/api/v1/people/match"
                match_payload = {"id": p.get("id")}
                try:
                    m_resp = requests.post(match_url, headers=headers, json=match_payload, timeout=REQUEST_TIMEOUT)
                    if m_resp.status_code == 200:
                        m_data = m_resp.json()
                        person_obj = m_data.get("person", {})
                        if person_obj.get("email"):
                            email = person_obj.get("email")
                        if person_obj.get("name"):
                            name = person_obj.get("name")
                        if person_obj.get("linkedin_url"):
                            linkedin = person_obj.get("linkedin_url")
                except Exception as exc:
                    logger.debug("Apollo Match API failed for person '%s': %s", name, exc)
            
            if name:
                contacts.append({
                    "name": name,
                    "title": title,
                    "email": email,
                    "linkedin_url": linkedin
                })
        return contacts
    except Exception as exc:
        logger.debug("Apollo API search failed for domain '%s': %s", domain, exc)
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich_leads(leads: List[dict]) -> List[dict]:
    """
    Enrich a list of lead dicts by filling in missing website_url and
    linkedin_url fields.
    """
    if not leads:
        return []

    use_serper = bool(SERPER_API_KEY)
    method = "Serper.dev Search" if use_serper else "local article scraping"
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

        if use_serper and company:
            # Use Serper Google Search
            if not has_website:
                website = _find_website_via_serper(company)
                if website:
                    lead["website_url"] = website
                    logger.info("  -> Website found: %s", website)

            if not has_linkedin:
                linkedin = _find_linkedin_via_serper(company)
                if linkedin:
                    lead["linkedin_url"] = linkedin
                    logger.info("  -> LinkedIn found: %s", linkedin)

        # Local fallback for any still-missing fields
        if not lead.get("website_url") or not lead.get("linkedin_url"):
            local = _local_extract(source_url, company)
            if local.get("website_url") and not lead.get("website_url"):
                lead["website_url"] = local["website_url"]
                logger.info("  -> Website (local fallback): %s", local["website_url"])
            if local.get("linkedin_url") and not lead.get("linkedin_url"):
                lead["linkedin_url"] = local["linkedin_url"]
                logger.info("  -> LinkedIn (local fallback): %s", local["linkedin_url"])

        # Fetch Contacts via Apollo.io
        lead["key_contacts"] = lead.get("key_contacts", [])
        if lead.get("website_url") and APOLLO_API_KEY:
            from urllib.parse import urlparse
            domain = urlparse(lead["website_url"]).netloc.lower().replace("www.", "")
            if domain:
                logger.info("  -> Finding contacts via Apollo for domain: %s", domain)
                apollo_contacts = _apollo_find_contacts(domain)
                if apollo_contacts:
                    logger.info("  -> Found %d contacts via Apollo", len(apollo_contacts))
                    # Merge with existing people extracted from article
                    existing_names = {c.get("name", "").lower() for c in lead["key_contacts"] if isinstance(c, dict)}
                    for ac in apollo_contacts:
                        if ac["name"].lower() not in existing_names:
                            lead["key_contacts"].append(ac)
                        else:
                            # Update existing contact with email if found
                            for ec in lead["key_contacts"]:
                                if isinstance(ec, dict) and ec.get("name", "").lower() == ac["name"].lower():
                                    if ac.get("email") and not ec.get("email"):
                                        ec["email"] = ac["email"]
                                    if ac.get("title") and not ec.get("title"):
                                        ec["title"] = ac["title"]
                                    if ac.get("linkedin_url") and not ec.get("linkedin_url"):
                                        ec["linkedin_url"] = ac["linkedin_url"]

        # Fallback for missing person LinkedIn IDs
        if use_serper and company:
            for c in lead["key_contacts"]:
                if isinstance(c, dict):
                    if c.get("name") and not c.get("linkedin_url"):
                        logger.info("  -> Fallback LinkedIn search for person: %s", c.get("name"))
                        li = _find_person_linkedin_via_serper(c.get("name"), company)
                        if li:
                            c["linkedin_url"] = li
                            logger.info("  -> Found person LinkedIn: %s", li)

        # Format key_contacts into a readable string for Google Sheets
        contacts_str_list = []
        for c in lead["key_contacts"]:
            if isinstance(c, dict):
                c_name = c.get("name", "")
                c_title = c.get("title", "Executive")
                c_email = c.get("email", "")
                c_linkedin = c.get("linkedin_url", "")
                
                parts = []
                parts.append(f"{c_name} ({c_title})")
                if c_email:
                    parts.append(f"Email: {c_email}")
                if c_linkedin:
                    parts.append(f"LinkedIn: {c_linkedin}")
                contacts_str_list.append(" - ".join(parts))
            elif isinstance(c, str):
                contacts_str_list.append(c)

        lead["contacts_formatted"] = "\n".join(contacts_str_list)

        enriched.append(lead)

    filled_web = sum(1 for l in enriched if l.get("website_url"))
    filled_li = sum(1 for l in enriched if l.get("linkedin_url"))
    logger.info(
        "Enrichment done: %d/%d have website, %d/%d have LinkedIn.",
        filled_web, len(enriched), filled_li, len(enriched),
    )

    return enriched
