"""
src/email_generator.py
----------------------
Generates personalized Gmail compose links using Groq AI for leads.
"""

import logging
import os
import json
import urllib.parse
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
if _GROQ_API_KEY:
    _client = Groq(api_key=_GROQ_API_KEY)
else:
    _client = None

_MODEL = "llama-3.3-70b-versatile"

CURATO_TEMPLATE = """We help fast-growing startups like yours scale their brand, messaging, and digital presence to match their momentum. 

Are you open to a brief chat next week to see if we'd be a good fit for your current growth stage?"""

def generate_compose_link(person: dict, lead: dict) -> str:
    """
    Generate a personalized Gmail compose link for the given person and lead.
    If the person lacks a public email, it will still generate a compose link with a blank 'To' field.
    """
    email = person.get("Public Email", "").strip()
        
    if _client is None:
        logger.error("Groq client not initialized — skipping email generation.")
        return ""
        
    person_name = person.get("Person Name", "there")
    company_name = person.get("Company Name", "your company")
    why_this_lead = lead.get("why_this_lead", "")
    funding_amount = lead.get("funding_amount", "")
    
    prompt = f"""You are writing a cold outreach email.
Generate exactly TWO things in a valid JSON object:
1. "subject": A catchy, personalized subject line (max 8 words).
2. "opening": 2-3 short, personalized opening sentences acknowledging their recent funding/news and congratulating them.

Context:
- Person Name: {person_name}
- Company: {company_name}
- Funding Amount: {funding_amount}
- Lead Context: {why_this_lead}

Return ONLY valid JSON in this format:
{{
    "subject": "string",
    "opening": "string"
}}
"""

    try:
        response = _client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": "You are a top-tier B2B sales copywriter. Output strictly valid JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        
        subject = data.get("subject", f"Congrats on the momentum at {company_name}")
        opening = data.get("opening", f"Congratulations on the recent growth and funding at {company_name}!")
        
    except Exception as exc:
        logger.error("Groq API error during email generation for '%s': %s", company_name, exc)
        return ""

    # Construct the full email body
    first_name = person_name.split(" ")[0] if person_name else "there"
    full_body = f"Hi {first_name},\n\n{opening}\n\n{CURATO_TEMPLATE}\n\nRegards,\n\nCurato Team"
    
    # URL encode parameters
    params = {
        'view': 'cm',
        'fs': '1',
        'to': email,
        'su': subject,
        'body': full_body
    }
    encoded_params = urllib.parse.urlencode(params)
    gmail_url = f"https://mail.google.com/mail/?{encoded_params}"
    
    # Format as Google Sheets HYPERLINK formula
    # Note: Google sheets hyperlink formula syntax is =HYPERLINK("url", "label")
    return f'=HYPERLINK("{gmail_url}", "📧 Compose Email")'
