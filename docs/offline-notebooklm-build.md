# Offline, Zero-Egress NotebookLM — Build Runbook

**Paste this whole file into Claude Code.** It's a directive for you (Claude Code) to execute, with a few steps I have to do by hand in a GUI.

---

## Context for Claude Code

We're standing up a **completely offline, zero-egress** NotebookLM alternative on a **2026 14" MacBook Pro, M5 Pro, 24GB unified memory**. Documents (including clinical material) must never traverse the network. The LLM runs **natively** for Metal; everything else runs in Docker; egress is enforced by a firewall at the end.

**Cardinal rule:** do every install/download step while online. Apply the LuLu firewall **dead last** — if you cut egress first, the downloads fail.

**Step markers:**
- Unmarked steps → you (Claude Code) run them in the integrated terminal.
- `⚠️ MANUAL` → a GUI step I do myself. Stop, tell me exactly what to do, and wait.
- `🔎 VERIFY` → confirm a current value (model tag, API signature, file path) against the live source before running, because it drifts between versions. Don't hardcode blindly.

**Two things you must verify before relying on them (they change often):**
1. The exact Qwen3.5-9B **MLX** model name in LM Studio's search, and the exact OpenMed + Docling Python API signatures (`deidentify`, `analyze_text`, the Docling converter call).
2. Open Notebook's current **retrieval function** location for the reranker patch — inspect the repo/image rather than assuming a path.

**The locked architecture (don't substitute components):**

| Layer | Choice | Runs in |
|---|---|---|
| LLM | Qwen3.5-9B (MLX, ~6-bit, ~7GB) | LM Studio, **native** |
| Embedder | BAAI/bge-m3 | Infinity, Docker |
| Reranker | BAAI/bge-reranker-v2-m3 | Infinity, Docker |
| Parse | Docling (PDF→markdown) | native Python |
| De-identify + NER | OpenMed (library only) | native Python (MLX) |
| Notebook/RAG app | Open Notebook | Docker |
| Vector + data store | SurrealDB v2 | Docker |
| TTS + STT | Speaches (Kokoro + Whisper) | Docker |
| Container runtime | Docker Desktop | — |
| Egress control | LuLu (applied last) | — |

**Topology:** containers reach each other by service name (`surrealdb`, `infinity`, `speaches`); the only host service is LM Studio, reached at `host.docker.internal:1234`.

---

## Phase 0 — Prereqs (ONLINE)

```bash
brew install --cask docker lm-studio lulu
# Launch Docker Desktop once so the daemon is running, then:
```

`⚠️ MANUAL` — Docker Desktop → Settings → Resources → **Memory = 7 GB**. This is the hard ceiling on the entire container side so it can't starve macOS or LM Studio. Tell me when done.

Make the project directory:

```bash
mkdir -p ~/offline-notebook/{raw_pdfs,clean_sources,infinity_cache,surreal_data,notebook_data}
cd ~/offline-notebook
```

---

## Phase 1 — Native ingest toolchain: Docling + OpenMed (ONLINE)

This runs on the host (not Docker) so OpenMed gets Apple MLX acceleration. It's the **front-door de-identification gate**: PHI is stripped here, before anything is embedded or stored.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install docling "openmed[mlx]"
```

`🔎 VERIFY` the OpenMed model IDs and API at https://openmed.life/docs/ (de-identification guide + `analyze_text`). Then pre-download the two models we use so nothing fetches at runtime:
- PII / de-identification model (HIPAA Safe Harbor, 18 identifiers)
- `OpenMed/OpenMed-NER-OncologyDetect-MultiMed-568M` (oncology entity tagging)

Create `src/ingest.py`. **This is a contract, not final code** — `🔎 VERIFY` the exact `docling` and `openmed` call signatures against their docs and fix the marked lines:

```python
#!/usr/bin/env python3
"""raw_pdfs/*.pdf -> Docling parse -> OpenMed de-id -> oncology NER frontmatter
-> clean_sources/*.md  (de-identified; safe to hand to Open Notebook)."""
import pathlib, yaml
from docling.document_converter import DocumentConverter
import openmed  # 🔎 VERIFY import surface

SRC = pathlib.Path("raw_pdfs"); OUT = pathlib.Path("clean_sources"); OUT.mkdir(exist_ok=True)
converter = DocumentConverter()

# 🔎 VERIFY: construct the de-id pipeline (prod profile) and the oncology NER model.
# Per the docs, de-id exposes deidentify(...)/analyze_text(...); choose a redaction
# method (mask with [LABELS], shift dates, or deterministic Faker surrogates).
deid = openmed.OpenMedConfig.from_profile("prod")        # 🔎 VERIFY
ner  = openmed.load("OpenMed-NER-OncologyDetect-MultiMed-568M")  # 🔎 VERIFY

for pdf in sorted(SRC.glob("*.pdf")):
    md = converter.convert(str(pdf)).document.export_to_markdown()  # 🔎 VERIFY
    clean = openmed.deidentify(md, config=deid)                     # 🔎 VERIFY
    ents  = ner(clean)                                              # 🔎 VERIFY
    tags  = sorted({e["label"] + ":" + e["text"] for e in ents})   # 🔎 VERIFY shape
    fm = "---\n" + yaml.safe_dump({"source": pdf.name, "entities": tags}) + "---\n\n"
    (OUT / f"{pdf.stem}.md").write_text(fm + clean)
    print(f"✓ de-identified + tagged: {pdf.name}")
```

Smoke-test it on one throwaway PDF and **show me the output `.md`** so I can eyeball that identifiers are actually gone before we trust the pipeline.

---

## Phase 2 — Docker stack: SurrealDB + Infinity + Open Notebook + Speaches (ONLINE)

Generate the encryption key (store it once; if it changes, saved credentials become unreadable):

```bash
openssl rand -hex 32
```

Create `docker-compose.yml` (paste the key into `OPEN_NOTEBOOK_ENCRYPTION_KEY`):

```yaml
services:
  surrealdb:
    image: surrealdb/surrealdb:v2
    command: start --log info --user root --pass root rocksdb:/mydata/mydatabase.db
    user: root
    ports: ["8000:8000"]
    volumes: ["./surreal_data:/mydata"]
    environment: ["SURREAL_EXPERIMENTAL_GRAPHQL=true"]
    restart: always
    mem_limit: 2g

  infinity:
    image: michaelf34/infinity:latest-cpu
    command: >
      v2 --engine optimum
      --model-id BAAI/bge-m3
      --model-id BAAI/bge-reranker-v2-m3
      --port 7997 --url-prefix /v1
    ports: ["7997:7997"]
    volumes: ["./infinity_cache:/app/.cache"]
    environment: ["INFINITY_ANONYMOUS_USAGE_STATS=0"]   # disable telemetry
    restart: always
    mem_limit: 4g

  open_notebook:
    image: lfnovo/open_notebook:v1-latest
    ports: ["8502:8502", "5055:5055"]     # UI + REST API (keep 5055 exposed)
    environment:
      - OPEN_NOTEBOOK_ENCRYPTION_KEY=PASTE-HEX-KEY-HERE
      - SURREAL_URL=ws://surrealdb:8000/rpc
      - SURREAL_USER=root
      - SURREAL_PASSWORD=root
      - SURREAL_NAMESPACE=open_notebook
      - SURREAL_DATABASE=open_notebook
      - OPEN_NOTEBOOK_EMBEDDING_BATCH_SIZE=8
    volumes: ["./notebook_data:/app/data"]
    depends_on: ["surrealdb", "infinity"]
    restart: always
    mem_limit: 2g

  speaches:
    image: ghcr.io/speaches-ai/speaches:latest-cpu
    container_name: speaches
    ports: ["8969:8000"]
    volumes: ["hf-hub-cache:/home/ubuntu/.cache/huggingface/hub"]
    restart: unless-stopped
    mem_limit: 3g
    cpus: 4

volumes:
  hf-hub-cache:
```

Bring it up and pull the audio models:

```bash
docker compose up -d
sleep 15

# Kokoro (TTS, ~500MB) + a Whisper model (STT) into Speaches:
docker compose exec speaches uv tool run speaches-cli model download speaches-ai/Kokoro-82M-v1.0-ONNX
docker compose exec speaches uv tool run speaches-cli model download speaches-ai/whisper-large-v3-turbo  # 🔎 VERIFY id

# Infinity pulls bge-m3 + bge-reranker-v2-m3 on first call; warm them:
curl -s http://localhost:7997/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"BAAI/bge-m3","input":"warmup"}' | head -c 200 ; echo

curl -s http://localhost:7997/v1/rerank \
  -H "Content-Type: application/json" \
  -d '{"model":"BAAI/bge-reranker-v2-m3","query":"chest pain","documents":["myocardial infarction","a recipe for soup"],"top_n":2}' ; echo
```

Both curls should return JSON (embeddings vector; ranked docs with the MI line scoring highest). If so, the embed + rerank backend is live.

---

## Phase 3 — Patch Open Notebook to use the reranker

Open Notebook has **no native reranker role**, so this is the one code change. Implement it as a small, flag-guarded patch.

`🔎 VERIFY` by inspecting the repo (https://github.com/lfnovo/open-notebook) or the running image: find the RAG retrieval step — the function that queries SurrealDB for relevant chunks and assembles the context passed to the LLM (search/query/RAG module).

Apply this **contract**:
1. Retrieve the top **20** candidates from vector search (raise the existing top-k).
2. POST to the Infinity reranker (container-to-container, service name):
   ```
   POST http://infinity:7997/v1/rerank
   {"model":"BAAI/bge-reranker-v2-m3","query":<user query>,
    "documents":[<the 20 chunk texts>],"top_n":5}
   ```
3. Reorder by the returned scores; pass **only the top 5** into the LLM prompt.
4. Gate it behind an env flag (e.g. `RERANK_ENABLED=true`, `RERANK_TOPN=5`) so it's trivial to toggle and survives upgrades.

Keep the patch in a small file / clearly-commented block, and note in the project README how to re-apply it after an Open Notebook image bump (we pin the tag, so this is rare).

---

## Phase 4 — LM Studio (native, MLX) — LLM only

`⚠️ MANUAL` — I'll do this in the LM Studio app:
- Load chat model: search **Qwen3.5-9B**, pick an **MLX** build (~6-bit, ~7GB). `🔎 VERIFY` exact name. (Optional second model: Qwen3.6-27B MLX 4-bit, ~17GB, as a *chat-only* mode I load when I'm not generating audio.)
- Load settings → **Context Length = 8192** (the single biggest "won't explode" lever).
- Enable **JIT / auto-unload** of idle models (release memory between tasks).
- Developer/Local Server tab → **Start** (port **1234**).

Embeddings do **not** come from LM Studio in this build — they come from Infinity. LM Studio serves the LLM only.

---

## Phase 5 — Wire the providers in Open Notebook UI

`⚠️ MANUAL` — at http://localhost:8502 → Settings → API Keys (and Models). I'll enter these:

- **LLM** — provider *OpenAI-Compatible*, base URL `http://host.docker.internal:1234/v1`, key `lm-studio` → Save → Test → Discover/Register (Qwen appears).
- **Embedding** — provider *OpenAI-Compatible*, base URL `http://infinity:7997/v1`, model `BAAI/bge-m3` → Save → Test.
- **TTS + STT** — provider *OpenAI-Compatible*, base URL `http://speaches:8000/v1`. Then Settings → Models → Add Model:
  - Text-to-Speech: `speaches-ai/Kokoro-82M-v1.0-ONNX`, display "Local TTS".
  - Speech-to-Text: `speaches-ai/whisper-large-v3-turbo`, display "Local STT".
- **Default Model Assignments:** Language = Qwen, Embedding = bge-m3, TTS = Local TTS, STT = Local STT.
- **Podcast / Episode Profile:** Host voice `af_bella`, Guest voice `am_adam`.

`🔎 VERIFY` for Claude Code: confirm Open Notebook resolves container service names (`infinity`, `speaches`) from its own container; if a given field insists on a host-reachable URL, fall back to `http://host.docker.internal:7997/v1` / `:8969/v1`.

---

## Phase 6 — How to ingest documents (the daily workflow)

1. Drop PDFs into `~/offline-notebook/raw_pdfs/`.
2. `source .venv/bin/activate && python src/ingest.py` → writes de-identified, tagged `.md` into `clean_sources/`.
3. In Open Notebook, add the files from `clean_sources/` as **local file** sources.

De-identification happens in step 2, **before** Open Notebook ever sees the text — so PHI never enters the index. Only add local files; a web/YouTube URL source would make an outbound fetch, which defeats the no-egress goal.

---

## Phase 7 — Lock egress with LuLu (DO THIS LAST)

`⚠️ MANUAL` — only after everything above works end to end:
- Open LuLu, approve its system extension.
- As prompts appear, set **BLOCK (deny outbound)** for: the **LM Studio** process, **Docker's** backend/networking helper processes, and the **Python** process running `src/ingest.py`. Allow them nothing.
- Loopback / localhost is local traffic, not egress — the `:1234` / `:7997` / `:8969` / `:8502` wiring keeps working.
- Maximum-paranoia option for a sensitive session: just turn Wi-Fi off; the whole stack still runs.

---

## Verify it's healthy

```bash
docker stats --no-stream     # surrealdb, infinity, open_notebook, speaches each under their caps
```

`⚠️ MANUAL` — Activity Monitor → Memory → **Memory Pressure** graph should sit **green** during a chat. Creeping yellow → drop LM Studio context to 4096, or confirm Infinity is running int8.

**Rough chat-time budget:** macOS ~6GB + LM Studio (Qwen 9B + 8K KV) ~8GB + Docker side (SurrealDB + Open Notebook + Infinity int8) ~5.5GB ≈ **~19–20GB**, leaving ~4–5GB free. Podcast generation spins up Speaches — sequence it after the script is written, not during heavy chat. This is why the 27B is a deliberate swap-in, never the default.

---

## Maintenance / durability

- **Pin image tags** once it all works (`surrealdb/surrealdb:v2`, `michaelf34/infinity:<x.x.x>-cpu`, `lfnovo/open_notebook:<exact>`, `speaches:<exact>`) so an upstream change can't break an offline session. The reranker patch is keyed to the Open Notebook version, so re-check it on any deliberate bump.
- **Back up** `./surreal_data` (tar it) before any upgrade.
- This is a study/synthesis tool over your own material: every answer is a pointer back to its cited source to verify, not an authority — especially for clinical content.

---

### First-run order recap
Phase 0 → 1 (test ingest) → 2 (stack up, models warm) → 3 (rerank patch) → 4 (LM Studio server on) → 5 (wire providers) → 6 (ingest real docs) → **7 (firewall, last)**.
