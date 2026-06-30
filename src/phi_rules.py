"""Deterministic PHI rules applied AFTER OpenMed NER de-id.

NER catches fuzzy identifiers (names, orgs, locations); these regex rules backstop the
*rule-shaped* cases NER reliably misses — found via deid_redteam.py:

  1. HIPAA Safe Harbor age aggregation: ages >89 must collapse to "90+" (the very old are
     re-identifiable). NER leaves ages in the clear.
  2. Address unit/apartment numbers, which survive when the street is caught separately.

Conservative by design: the age rule only matches 90-199 (never 55-year-old, never doses/years);
the unit rule uses apt/apartment/suite/ste only (NOT bare "unit", which collides with "units of ...").
"""
import re

# 90-199 immediately followed by a year/age token  ->  aggregate to "90+"
_AGE_OVER_89 = re.compile(r'\b(?:9\d|1\d{2})[-\s]?(?:year|yr|y/?o)s?(?:[-\s]?old)?\b', re.I)
# apartment / suite designators + their unit token
_ADDR_UNIT = re.compile(r'\b(?:apt\.?|apartment|suite|ste\.?)\s*#?\s*\w+', re.I)


def post_redact(text: str) -> str:
    text = _AGE_OVER_89.sub('[age 90+]', text)
    text = _ADDR_UNIT.sub('[unit]', text)
    return text
