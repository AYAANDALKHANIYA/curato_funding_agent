import os
import json
import requests

APOLLO_API_KEY = "GlSeTCQnSaqaOxUfoVQWJg"
domain = "cred.club"

url = "https://api.apollo.io/api/v1/people/search"
headers = {
    "Content-Type": "application/json", 
    "Cache-Control": "no-cache",
    "X-Api-Key": APOLLO_API_KEY
}

payload = {
    "q_organization_domains": domain,
    "person_titles": [
        "cmo", "vp marketing", "ceo"
    ],
    "per_page": 2
}

resp = requests.post(url, headers=headers, json=payload)
data = resp.json()

print(json.dumps(data, indent=2))
