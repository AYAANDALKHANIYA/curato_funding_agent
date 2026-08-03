"""
src/people_enricher.py
----------------------
Extracts the highest-ranking public contact from a lead's existing enriched contacts.
"""

from datetime import datetime

def extract_best_person(lead: dict) -> dict:
    """
    Given a lead dictionary with 'key_contacts', find the best single contact
    according to priority: Founder > Co-Founder > CEO > Managing Director.
    If none match specifically, pick the first available.
    """
    contacts = lead.get("key_contacts", [])
    if not contacts:
        return None

    company_name = lead.get("company_name", "")

    # Clean contacts to dictionaries if they are strings
    parsed_contacts = []
    for c in contacts:
        if isinstance(c, dict):
            if c.get("name"):
                parsed_contacts.append(c)
        elif isinstance(c, str):
            # Try to parse string "Name (Title) - Email: xxx" just in case
            pass # Mostly Apollo returns dicts, strings were generated in format, but original is preserved in key_contacts

    if not parsed_contacts:
        return None

    # Priority mapping
    def get_priority(title: str) -> int:
        t = title.lower()
        if "founder" in t and "co-founder" not in t:
            return 1
        if "co-founder" in t:
            return 2
        if "ceo" in t or "chief executive officer" in t:
            return 3
        if "managing director" in t:
            return 4
        # Default priority for any other executive
        return 99

    # Sort contacts by priority
    parsed_contacts.sort(key=lambda c: get_priority(c.get("title", "")))

    best = parsed_contacts[0]

    return {
        "Company Name": company_name,
        "Person Name": best.get("name", ""),
        "Designation": best.get("title", ""),
        "LinkedIn Profile": best.get("linkedin_url", ""),
        "Public Email": best.get("email", ""),
        "Collected At": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    }
