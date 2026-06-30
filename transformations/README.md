# Ready-made Transformations

[Transformations](https://www.open-notebook.ai/features/transformations) are reusable AI actions
Open Notebook runs over a source. These two cover the common "study" asks that Open Notebook has
no dedicated button for — **flashcards** and **board-style questions**. The output is saved as an
insight on the source, which you can keep or "save as note."

## Load them

**Fastest (API).** With the stack up, run once:
```bash
python transformations/seed_transformations.py
```
It skips any transformation whose name already exists, so it's safe to re-run.

**Or by hand (UI).** Settings → Transformations → New, and fill the four fields from each section
below. Then on any source, click **Run transformation**, pick one, and read the result.

> **PHI still applies.** These run on whatever text is in the source and are instructed to drop
> identifiers — but treat that as a backstop, not a guarantee. Only run them on material that went
> through the `raw_pdfs/` de-id gate or is guaranteed PHI-free (see the upload rule in the main
> [README](../README.md#using-it-day-to-day)).

---

## 1. Flashcards

- **Name / Title:** `Flashcards`
- **Description:** High-yield Q&A flashcards from this source (Anki-friendly).
- **Prompt:**

```
You are a medical educator creating study flashcards from the source content provided.

Produce high-yield, atomic flashcards — each testing exactly one fact or concept. Favor
mechanisms, definitions, diagnostic criteria, first-line treatments, dosing thresholds, and
classic associations. Skip anything trivial or administrative.

Rules:
- One discrete fact per card. If a card needs an "and", split it into two.
- Front: a specific question or cue with a single correct answer — no vague "tell me about X".
- Back: the answer in as few words as carry the meaning, plus a short "why" clause only when it
  genuinely aids recall.
- Stay strictly faithful to the source. Do not add facts it doesn't support; if the source is
  thin, write fewer cards rather than inventing.
- Include no patient identifiers (names, dates, MRNs, locations) even if they appear in the source.

Output a Markdown table so it reads cleanly and can be exported to Anki:

| Front | Back |
|---|---|
| ... | ... |

Write 10-20 cards depending on how much the source supports.
```

## 2. Board-style Q&A

- **Name:** `Board-style Q&A`  ·  **Title:** `Board-style questions`
- **Description:** USMLE-style single-best-answer questions with answers and explanations.
- **Prompt:**

```
You are an item writer for a medical licensing exam, drafting practice questions from the source
content provided.

Write 3-5 single-best-answer, USMLE-style questions that test application and reasoning, not rote
recall. Every question must be answerable from the source; do not test facts it doesn't support,
and invent no numbers.

For each question:
1. A short clinical vignette stem when the content supports one; otherwise a focused conceptual stem.
2. Five homogeneous options labeled A-E (same category, all plausible), with exactly one best answer.
3. The correct answer.
4. A brief explanation: why the answer is right, then one line per distractor on why it's wrong.

Constraints:
- Faithful to the source — no outside facts.
- No patient identifiers; if the source contains any, write around them with generic descriptors
  ("a 64-year-old man").
- Calibrate to Step 1 / Step 2 CK difficulty.

Format each item exactly as:

**Q1.** [stem]
- A. ...
- B. ...
- C. ...
- D. ...
- E. ...

**Answer:** [letter] — [one-line rationale]
**Why not:** A: ... · B: ... · C: ... · D: ... · E: ...
```

## 3. Clinical Pearls

- **Name / Title:** `Clinical Pearls`
- **Description:** High-yield clinical takeaways and pearls from this source.
- **Prompt:**

```
You are a clinician-educator distilling the source content into high-yield clinical pearls.

Extract only the points worth remembering at the bedside — the bottom-line teaching points, not a
full summary. Each pearl is one tight, actionable sentence. Prefer: when to suspect, how to
confirm, first-line management, dosing thresholds, red flags, and common pitfalls.

Rules:
- Faithful to the source only — no outside facts, no invented numbers. Fewer pearls beats padded ones.
- Lead with the highest-yield points.
- Plain, declarative sentences; no hedging.
- No patient identifiers (names, dates, MRNs, locations).

Format as grouped bullets; omit any heading the source doesn't support:

**Diagnosis**
- ...

**Management**
- ...

**Pitfalls & pearls**
- ...
```

## 4. Patient Explainer

- **Name:** `Patient Explainer`  ·  **Title:** `Patient FAQ`
- **Description:** Plain-language patient-facing Q&A from this source (no jargon).
- **Prompt:**

```
You are explaining the source content to a patient with no medical background.

Write a short FAQ — the questions a patient or family member would actually ask — and answer each
in plain language at roughly an 8th-grade reading level. Translate jargon ("hypertension" becomes
"high blood pressure") and briefly define any term you can't avoid.

Rules:
- Faithful to the source; add no medical advice or facts it doesn't contain. If the source doesn't
  answer a natural question, say what it does cover instead of guessing.
- Warm, clear, and calm — never alarming, never condescending.
- No patient identifiers.
- End with one line: "This is general information from one source, not medical advice — talk to
  your clinician about your situation."

Format:

**Q: ...**
A: ...

**Q: ...**
A: ...
```

---

## Tips

- The exact prompts above are also defined in
  [`seed_transformations.py`](seed_transformations.py) — edit there and re-run to update.
- A global **Default Transformation Prompt** (Settings → Transformations) is prepended to *every*
  transformation — a good place for house style ("be concise", "use standard AMA abbreviations").
- To suggest one automatically on new sources, set its **Apply default** toggle (or
  `apply_default: True` in the seed script).
