# Offline NotebookLM for Clinical Documents

A NotebookLM-style research assistant that runs entirely on one laptop. Drop in
clinical PDFs, ask questions, get answers with citations back to the source — and
nothing ever leaves the machine: not a document, not an identifier, not a query.

The piece doing the medical heavy lifting is **OpenMed**: an open-source suite of local
medical NLP models that de-identifies and tags documents before they're indexed. PHI
stripping is one of the things OpenMed does here; the broader point is that you can run real
medical NLP locally, on hardware you control, with the network turned off.

> **⚠️ Do not upload PHI.** Do not put protected health information or patient data into this
> tool **unless you have explicit permission from your employer**, and **defer to your
> hospital's policy on how — and whether — PHI may be stored.** The OpenMed PHI screener and the
> LuLu egress firewall are here only as a **contingency** — a backstop if something slips
> through — **not** authorization to load patient data. Where this guidance and your
> institution's policy differ, the institution's policy governs.
>
> **Critical:** the de-id gate only runs on files dropped in `raw_pdfs/`. Anything from a
> patient chart must go through that folder — never the UI's "Add Source" — even if you've read
> it and believe it's clean (see **Using it day to day**).

Used as intended — *without* PHI — it's a capable offline workspace: **personal notes and
documentation, literature and research reading, exam or board studying, and a private
clinical-knowledge base you can query with no network connection at all.** That's the default,
recommended way to run it.

---

## Why this exists

Cloud tools like NotebookLM and ChatGPT are off-limits for anything with PHI — the
documents would leave your control the moment you upload them. Running a local LLM
solves half of that: the *model* stays on the machine. But the documents still arrive
full of names, dates, MRNs, and addresses, and the moment they're chunked and embedded
into a vector store, those identifiers are in the index.

So the interesting problem isn't the chat box. It's the gate in front of the index —
something that strips identifiers and recognizes clinical entities, locally, before any
text is stored. That gate is OpenMed.

## What OpenMed does here

OpenMed is the medical-NLP layer of the pipeline. It runs natively (Apple MLX, no
container) so it's fast, and it sits in front of everything else.

- **De-identification** — strips the 18 HIPAA Safe Harbor identifiers using a local
  PII model (`OpenMed-PII-QwenMed-XLarge-600M-v1`). Dates are *shifted*, not blanked,
  so intervals between events survive. Backed by `src/phi_rules.py` for the edge cases the
  model misses (ages over 89, address subunits).
- **Clinical entity recognition** — tags entities into each document's frontmatter
  (e.g. oncology, via `OpenMed-NER-OncologyDetect-MultiMed-568M`), so the corpus is
  *enriched*, not merely redacted.
- **A standing regression test** — `src/deid_redteam.py` runs 21 adversarial PHI cases and
  must pass 21/21. If it ever drops, the gate is leaking and ingestion should stop.

Because this runs before Open Notebook ever sees the text, identifiers are stripped before
anything is stored. Treat it as a screener, not a guarantee — see the note on patient data
above, and follow your hospital's policy.

## How it fits together

```
  PDF
   │  Docling            parse to markdown
   ▼
  OpenMed                de-identify  +  tag clinical entities      ← the gate
   │
   ▼
  clean markdown
   │  Open Notebook      chunk → embed (Infinity / bge-m3) → store (SurrealDB)
   ▼
  your question  →  retrieve  →  rerank (bge-reranker-v2-m3)  →  Gemma LLM  →  cited answer
```

| Layer | Component | Runs in |
|---|---|---|
| LLM | Gemma 4 E4B *(default)* or Qwen3.5-9B (MLX) | LM Studio, native (host `:1234`) |
| Embed + rerank | bge-m3 + bge-reranker-v2-m3 | Infinity, Docker (`:7997`) — custom arm64 build |
| Parse + de-id + NER | Docling + **OpenMed** | native Python venv (`./.venv`) |
| Notebook / RAG | Open Notebook | Docker (UI `:8502`, API `:5055`) |
| Vector + data store | SurrealDB v2 | Docker (`:8000`) |
| TTS + STT | Speaches (Kokoro + faster-whisper) | Docker (`:8969`) |
| Egress control | LuLu | host (armed last) |

Everything except the LLM runs in Docker and reaches the others by service name. The
LLM runs natively because that's how it gets Metal acceleration.

---

## What you can do with it

Open Notebook is the workspace layer, and it does more than answer questions. In this build
every feature runs against the **local** models — nothing reaches the network.

- **Chat with citations** — ask across a notebook's sources and get answers that cite where
  each claim came from, so you can verify. Multiple chat sessions per notebook, with
  fine-grained control over which sources are in context.
- **Multi-speaker podcasts (audio overviews)** — turn a notebook into a spoken episode: 1–4
  configurable voices via *Episode Profiles*, with as much script control as you want. Audio is
  generated locally by Speaches (Kokoro TTS); transcription of audio sources uses local Whisper.
- **Transformations** — reusable AI actions you run over a source: summaries, key insights,
  entity extraction, reflection questions, and any you write yourself. **Flashcards, study
  guides, and FAQ-style Q&A live here** — there's no separate "flashcards" button, but a
  transformation that emits them does the same job and you can reuse it across every source. Four
  ready-made ones (flashcards, board-style Q&A, clinical pearls, patient explainer) ship in
  [`transformations/`](transformations/).
- **Notes** — write them by hand or have the model draft them from a source, kept alongside the
  material.
- **Search** — full-text *and* semantic/vector search across all your notebooks (the vector side
  is bge-m3 via Infinity).
- **Multiple notebooks** — keep projects separate, each with its own sources, notes, and chats.
- **Broad source support** — PDFs, web links, YouTube, audio, video, Office docs, plain text,
  and more. *In this build, add files only through the `raw_pdfs/` de-id gate (or
  guaranteed-clean files via the UI). A web or YouTube source makes an outbound fetch — which
  breaks the no-egress guarantee — so leave those off for sensitive work.*
- **REST API** — all of the above is scriptable on the API at `:5055`; it's how this build wires
  its providers and how the watcher pushes de-identified docs in.

Out of the box Open Notebook also supports 18+ cloud AI providers and outbound MCP clients. This
build deliberately points every model at a local endpoint (LM Studio, Infinity, Speaches) and
arms the firewall, so none of that capability sends anything off the machine.

---

## Requirements

- **Apple-silicon Mac.** Built and tested on a 14" MacBook Pro (M5 Pro, 24 GB). Most of the
  memory footprint is the Docker side — Infinity alone runs two bge models — not the LLM, so
  24 GB is the comfortable floor either way. The default **Gemma 4 E4B** is the light end; the
  heavier **Qwen3.5-9B** option is what pushes a full session toward ~19–20 GB.
- **Docker Desktop**, **LM Studio**, **Homebrew**.
- **~15–20 GB free disk** for model weights (the two bge models are ~2 GB each; Gemma 4 E4B is
  a few GB, Qwen3.5-9B ~7 GB).
- An internet connection **for installation only.** Every download happens up front;
  the firewall goes on last.

## Installation

Do all of this online. The egress lockdown (step 9) comes dead last — cut the network
first and the downloads fail.

**1. Clone the repo**
```bash
git clone https://github.com/chadmarkey/offline-notebooklm.git
cd offline-notebooklm
```

**2. Install the host tools**
```bash
brew install --cask docker lm-studio lulu
```
Launch Docker Desktop once so the daemon starts. Then set **Settings → Resources →
Memory = 7 GB** — the hard ceiling for the whole container side, so it can't starve
macOS or LM Studio.

**3. Create the working directories** (they're gitignored, so a fresh clone won't have them)
```bash
mkdir -p raw_pdfs clean_sources infinity_cache surreal_data notebook_data
```

**4. Set the encryption key**
```bash
cp .env.example .env
openssl rand -hex 32          # paste the output into OPEN_NOTEBOOK_ENCRYPTION_KEY in .env
```
Open Notebook uses this key to encrypt stored provider credentials. Set it once and
don't change it — if it changes, saved credentials become unreadable.

**5. Build the OpenMed ingest toolchain** (the de-id gate, native for MLX)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install docling "openmed[mlx]"
python src/deid_redteam.py        # must print 21/21 before you trust the gate
```
The OpenMed models download on first ingest. To confirm the gate works, drop one
throwaway PDF in `raw_pdfs/`, run `python src/ingest.py`, and read the output in
`clean_sources/` — identifiers should be gone.

**6. Bring up the Docker stack**
```bash
docker compose up -d          # builds the arm64 Infinity image, starts all containers
docker compose ps             # every service should read "Up"
```
Warm the embedder and reranker (they pull bge-m3 + bge-reranker-v2-m3 on first call):
```bash
curl -s http://localhost:7997/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"BAAI/bge-m3","input":"warmup"}' | head -c 120 ; echo
```

**7. Start the LLM** (LM Studio, native)

In the LM Studio app: load a chat model — **Gemma 4 E4B** is the current default (light,
low memory); **Qwen3.5-9B** is the heavier alternative. Set a generous **Context Length —
32768**: 8192 is too small once Open Notebook adds retrieved chunks and your selection to the
prompt (you'll get *"Content too large for the selected model"*). Gemma 4 E4B supports 131072,
and its KV cache is cheap, so a big window costs almost nothing in memory. Set **Max Concurrency
= 1** for single-user use, then **Developer → Start Server** (port `1234`). Or from the terminal:
```bash
lms server start && lms load google/gemma-4-e4b -c 32768 --parallel 1
```

**8. Wire the providers in Open Notebook**

Open **http://localhost:8502 → Settings**, and add three OpenAI-compatible providers:
LLM at `http://host.docker.internal:1234/v1` (the LLM model name must match the chat model
you loaded in step 7), embedding at `http://infinity:7997/v1` (`BAAI/bge-m3`), and TTS/STT at
`http://speaches:8000/v1`. Exact values, model IDs, and the default-model assignments are in
**[RUNBOOK.md](docs/RUNBOOK.md)**.

**9. Lock down egress with LuLu** *(last)*

Open LuLu, approve its system extension, and **block outbound** for the LM Studio,
Docker, and Python (`src/ingest.py`) processes. Loopback traffic is local, not egress, so
the stack keeps working. Until this step is done, "zero-egress" is *not* enforced — for
a sensitive session before then, just turn Wi-Fi off.

---

## Using it day to day

```bash
docker compose up -d                              # 1. start the stack
lms server start && lms load <chat-model>         # 2. start the LLM (Gemma 4 E4B or qwen/qwen3.5-9b)
source .venv/bin/activate && python src/watch.py      # 3. start the ingest watcher (leave running)
open http://localhost:8502                        # 4. open the notebook
```

Then just **drop a PDF into `raw_pdfs/`** — about 25 seconds later it's de-identified,
tagged, and in your notebook. Processed originals move to `raw_pdfs/_processed/` (they
still contain PHI — delete them when you're done).

> **The folder is the only safe way in for anything chart-related.** Dropping a file in
> `raw_pdfs/` runs the OpenMed de-id gate; the UI's **"Add Source"** button does **not** — it
> indexes whatever you hand it, verbatim. So:
>
> - **Anything pulled from a patient chart goes through the folder — always,** even if you've
>   read it and believe it has no PHI. If you can't *100% guarantee* it's PHI-free, treat it as
>   chart material: folder only.
> - Use **"Add Source"** *only* for documents you can **100% guarantee** contain no PHI —
>   textbooks, published papers, guidelines, your own non-patient notes.

A one-card version of this lives in **[START_HERE.md](docs/START_HERE.md)**.

## A note on what this is

It's a study and synthesis tool over your own material — not an authority. Every answer
is a pointer back to a cited source you can verify, which matters most for clinical
content. And "offline" is a property you enforce (step 9), not one you assume.

## Where to go next

- **[RUNBOOK.md](docs/RUNBOOK.md)** — day-to-day operation, exact provider wiring, the
  reranker patch, maintenance, and the gotchas learned the hard way.
- **[offline-notebooklm-build.md](docs/offline-notebooklm-build.md)** — the from-scratch
  build directive and the design rationale behind each locked component choice.
- **[START_HERE.md](docs/START_HERE.md)** — the "every time you open it" checklist.

## Built on

Open-source work this stitches together — all of it runs locally:

- **[OpenMed](https://github.com/maziyarpanahi/openmed)** — local-first medical NLP: HIPAA PII
  de-identification and 1,000+ clinical NER models, Apple MLX–accelerated, nothing leaves the
  machine ([models](https://huggingface.co/OpenMed) · [docs](https://openmed.life/docs/)).
- **[Open Notebook](https://github.com/lfnovo/open-notebook)** — the open-source,
  NotebookLM-style RAG app: the UI, chunking, retrieval, and podcast generation.
- **[LM Studio](https://lmstudio.ai)** — runs the local LLM natively (Metal) behind an
  OpenAI-compatible server.

**The language model** is swappable — anything LM Studio can serve works. The two wired here:

- **[Gemma 4 E4B](https://ai.google.dev/gemma/docs/core)** *(default)* — Google's open-weight
  on-device model. "E4B" is an *effective*-parameter size: it runs in a small memory footprint
  (a few GB), which is what makes it the comfortable default on a laptop.
- **[Qwen3.5-9B](https://github.com/QwenLM)** — Alibaba's open-weight model (Apache-2.0). Larger
  and heavier, with more reasoning headroom when you have the memory to spare.

## License

[Apache-2.0](LICENSE).
