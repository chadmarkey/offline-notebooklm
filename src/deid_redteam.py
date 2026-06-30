#!/usr/bin/env python3
"""Adversarial red-team for the PHI de-id gate (mirrors ingest.py: shift_dates, 600M, thresh 0.5).

Each case = a synthetic snippet (fake data only) + the identifier token(s) that MUST be gone
after de-id. Re-run after any model/threshold change to catch recall regressions.

Note: shift_dates keeps the YEAR (HIPAA Safe Harbor permits year), so date cases target the
precise month/day, not the bare year.
"""
import openmed
from phi_rules import post_redact

MODEL = "OpenMed/OpenMed-PII-QwenMed-XLarge-600M-v1"
THRESH = 0.5
_CFG = openmed.OpenMedConfig(backend="hf")   # skip the MLX attempt -> clean output

CASES = [
    ("age over 89",         "The patient is a 94-year-old retired teacher.",            ["94-year"]),
    ("date precise (num)",  "Last clinic visit was 2025-11-02.",                        ["2025-11-02"]),
    ("date precise (dob)",  "DOB 03/14/1948, no known drug allergies.",                 ["03/14"]),
    ("date words",          "Next appointment is March 3rd, 2026.",                     ["March 3rd"]),
    ("hyphen/apostrophe",   "Seen by Dr. Mary-Kate O'Brien-Schmidt.",                   ["Mary-Kate", "O'Brien"]),
    ("east-asian name",     "Attending physician Dr. Hiroshi Tanaka.",                  ["Hiroshi", "Tanaka"]),
    ("arabic name",         "Patient Aisha Al-Rashid presented today.",                 ["Aisha", "Al-Rashid"]),
    ("name = common word",  "Patient April Day, referred by Dr. June Storm.",           ["April Day", "June Storm"]),
    ("initials",            "Dictated by R.K.; consent obtained from patient J.S.",     ["R.K.", "J.S."]),
    ("street address",      "Resides at 123 Main Street, Apartment 4B.",                ["123 Main", "4B"]),
    ("city + zip",          "Home address Cambridge, MA 02139.",                        ["Cambridge", "02139"]),
    ("named institution 1", "Transferred from Memorial Sloan Kettering.",               ["Sloan Kettering"]),
    ("named institution 2", "Prior records from Johns Hopkins Hospital.",               ["Johns Hopkins"]),
    ("relative names",      "Accompanied by his wife Susan and son Michael.",           ["Susan", "Michael"]),
    ("email",               "Patient portal login is john.doe@clinic.org.",            ["john.doe@clinic.org"]),
    ("url + ip",            "Uploaded via https://myhealth.example.org from 192.168.1.42.", ["myhealth.example.org", "192.168.1.42"]),
    ("ssn",                 "Social Security 123-45-6789 verified.",                    ["123-45-6789"]),
    ("mrn embedded",        "Reviewed chart MRN#0098123 in detail.",                    ["0098123"]),
    ("phone + fax",         "Call 617-555-0148 or fax 617-555-0149.",                   ["555-0148", "555-0149"]),
    ("device + account",    "Infusion pump serial DX-99281, account 4455-2210-9981.",   ["DX-99281", "4455-2210"]),
    ("vehicle plate",       "Arrived driving, license plate 8XYZ123.",                  ["8XYZ123"]),
]


def main():
    fails = []
    for cat, text, toks in CASES:
        out = post_redact(openmed.deidentify(text, method="shift_dates", model_name=MODEL,
                                             confidence_threshold=THRESH, use_safety_sweep=True,
                                             config=_CFG).deidentified_text)
        leaked = [t for t in toks if t.lower() in out.lower()]
        print(f"[{'LEAK' if leaked else 'pass'}] {cat:22s} {('leaked: ' + str(leaked)) if leaked else ''}")
        if leaked:
            fails.append((cat, leaked, text, out))

    print(f"\n=== {len(CASES) - len(fails)}/{len(CASES)} passed, {len(fails)} with leaks ===")
    for cat, leaked, text, out in fails:
        print(f"\n-- {cat}: leaked {leaked}\n   in : {text}\n   out: {out}")


if __name__ == "__main__":
    main()
