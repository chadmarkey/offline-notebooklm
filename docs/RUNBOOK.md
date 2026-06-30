# Offline, Zero-Egress NotebookLM

A fully local NotebookLM alternative. Documents (including clinical material) are
de-identified **before** anything is indexed, and — once LuLu is armed (Phase 7) — nothing
ever leaves the machine.

> **Patient data:** do **not** upload PHI unless you have **explicit employer permission**, and
> defer to hospital policy on whether/how PHI may be stored. The de-id screener and firewall are
> a contingency backstop — not a guarantee, not authorization. Without PHI it's a local
> research / study / clinical-reference tool.

## Architecture

| Layer | What | Runs in |
|---|---|---|
| LLM | Gemma 4 E4B *(default)* / Qwen3.5-9B (MLX) | **LM Studio**, native (host :1234) |
| Embed + Rerank | bge-m3 + bge-reranker-v2-m3 | **Infinity**, Docker (:7997) — *custom arm64 build* |
| Parse + De-id + NER | Docling + OpenMed | native Python venv (`./.venv`) |
| Notebook / RAG | Open Notebook | Docker (UI :8502, API :5055) |
| Vector + data store | SurrealDB v2 | Docker (:8000) |
| TTS + STT | Speaches (Kokoro + faster-whisper) | Docker (:8969) |
| Egress control | LuLu | host (arm LAST — Phase 7) |

## Start / stop

```bash
cd ~/offline-notebook
docker compose up -d        # SurrealDB, Infinity, Open Notebook, Speaches
docker compose ps           # all should read "Up"
# + start LM Studio, load your chat model (Gemma 4 E4B / Qwen3.5-9B), Developer tab -> Start Server (:1234)
```
Open the UI at **http://localhost:8502**. Stop with `docker compose down` (data persists in
`./surreal_data`, `./notebook_data`). **LM Studio must be running** for chat to work.

## Daily workflow — INGESTING DOCUMENTS (the de-id gate)

**Never add chart-derived material through Open Notebook's "Add Source" — that path has no
de-id and indexes whatever you give it.** Anything pulled from a patient chart goes through the
folder/de-id gate below, *always* — even if you've read it and believe it's PHI-free. Reserve
"Add Source" strictly for documents you can **100% guarantee** contain no PHI (textbooks,
papers, guidelines, your own non-patient notes). Use one of these instead:

**Recommended — the auto-watcher (`src/watch.py`).** Start it once and leave it running; then
just drop PDFs and they appear in your notebook, de-identified. No commands per file, no UI
upload — so a raw PHI file can't be accidentally uploaded un-scrubbed.
```bash
cd ~/offline-notebook && source .venv/bin/activate && python src/watch.py   # leave running
#  then drop any PDF into raw_pdfs/  ->  ~25s later it's in your notebook, scrubbed.
#  processed raw PDFs move to raw_pdfs/_processed/ (still contain PHI — delete when done).
```
Pushes to your first notebook by default; set `ON_NOTEBOOK=notebook:xxxx` to target another.

**Manual alternative (one-shot, no auto-push):**
```bash
python src/ingest.py        # scrub everything in raw_pdfs/ -> clean_sources/*.md
#  then Add Source in the UI, uploading the clean_sources/*.md (NEVER the raw PDF)
```

De-id config (in `src/ingest.py`): PII model `OpenMed-PII-QwenMed-XLarge-600M-v1`,
`method=shift_dates`, `confidence_threshold=0.5`, plus `src/phi_rules.py` (age >89, address units).
Both paths share `ingest.process_one()`. Regression test: `python src/deid_redteam.py` (must stay 21/21).

## Provider config (already wired)

All providers are `openai_compatible` in Open Notebook, configured via the backend API
(more reliable than the UI — the UI "Sync Models" button is broken in this build):
- **LLM:** `http://192.168.65.254:1234/v1` (literal Docker host-gateway IPv4 — *not*
  `host.docker.internal`, which resolves to an unroutable IPv6 first), key `lm-studio`, model = the
  chat model you loaded (Gemma 4 E4B by default; `qwen/qwen3.5-9b` also works)
- **Embedding:** `http://infinity:7997/v1`, `BAAI/bge-m3`
- **TTS/STT:** `http://speaches:8000/v1`, Kokoro + `deepdml/faster-whisper-large-v3-turbo-ct2`

To re-wire from scratch, use the ON API at `:5055`: `POST /api/credentials`,
`POST /api/credentials/{id}/register-models`, `PUT /api/models/defaults`.

## Reranker patch (Phase 3)

`patches/notebook.py` is a copy of Open Notebook's `domain/notebook.py` with an env-gated
reranker, bind-mounted over the container file. `vector_search` over-fetches `RERANK_FETCH`
candidates, sends them to the Infinity bge-reranker, returns the reordered top `RERANK_TOPN`.
Toggle with `RERANK_ENABLED` (compose env). Best-effort: falls back to vector order on failure.

**Re-apply after an Open Notebook image bump** (rare — we pin the tag):
```bash
docker compose pull open_notebook
docker cp "$(docker compose ps -q open_notebook):/app/open_notebook/domain/notebook.py" patches/notebook.py
# re-apply the `_rerank` + vector_search block (see the patch header comment), then:
docker compose up -d open_notebook
```

## Phase 7 — Lock egress with LuLu (do this LAST)

Until this is done, "zero-egress" is **not enforced**. Install + arm before real clinical use:
```bash
brew install --cask lulu     # didn't install in the first pass; install now
```
Open LuLu, approve its system extension, then as prompts appear set **BLOCK (deny outbound)**
for: the **LM Studio** process, **Docker** backend/networking helpers, and the **Python**
process running `src/ingest.py`. Loopback (`localhost`/container networking) is local, not egress,
so the stack keeps working. Max paranoia: just turn Wi-Fi off for a sensitive session.

## Maintenance

- **Pin image tags** once stable (currently `surrealdb:v2`, local `offline-notebook-infinity`,
  `lfnovo/open_notebook:v1-latest`, `speaches:latest-cpu`) so an upstream change can't break
  an offline session.
- **Back up** `./surreal_data` (tar it) before any upgrade.
- `.env` holds the Open Notebook encryption key — back it up; if lost, saved provider
  credentials become unreadable. (`.gitignore` keeps it + all data/source dirs out of git.)
- Infinity is a **custom arm64 image** (`infinity-arm64/`, pinned deps in `requirements.txt`) —
  the published `michaelf34/infinity` is amd64-only and crash-loops under Rosetta.

## Gotchas (learned the hard way)

- **LM Studio not chatting?** It must be loaded *and* serving on :1234. From the host check
  `http://localhost:1234/v1/models`; `192.168.65.254` is container-only and won't load in a browser.
- **"Content too large for the selected model"?** The LLM's context window is smaller than Open
  Notebook's assembled prompt (system + reranked chunks + your selected sources). Reload with a
  bigger window: `lms load google/gemma-4-e4b -c 32768 --parallel 1` (Gemma 4 E4B supports 131072;
  its KV cache is cheap, so memory barely moves — the load estimate is flat from 16K to 64K). 8192
  overflows on document chat. Keep **Max Concurrency = 1** and only one copy loaded — each slot
  reserves a full context's worth of KV.
- **Infinity OOM / crash-loop?** Needs `mem_limit: 6g` + `--batch-size 8` (two fp32 bge models).
- **Provider "Unexpected endpoint"?** Base URL must end in `/v1` exactly once (ON appends `/models`).
- **Chrome autofill** stuffs the provider form with junk — clear the fields before saving.
