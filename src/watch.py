#!/usr/bin/env python3
"""Auto-ingest watcher for the offline NotebookLM.

Watches raw_pdfs/. The moment a PDF lands, it is de-identified (via the same verified
ingest.process_one pipeline) and the cleaned text is pushed straight into Open Notebook —
no manual `python ingest.py`, no UI upload. Because ingestion never touches the UI, a raw
PHI file can't accidentally be uploaded un-scrubbed.

    cd ~/offline-notebook && source .venv/bin/activate && python watch.py

Stop with Ctrl-C. Processed raw PDFs are moved to raw_pdfs/_processed/ (still contain PHI —
delete when you no longer need the originals). Config via env:
    ON_API       Open Notebook API base   (default http://localhost:5055)
    ON_NOTEBOOK  target notebook id       (default: first non-archived notebook)
    POLL         seconds between scans     (default 4)
"""
import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

import ingest  # reuses the verified de-id + NER pipeline (process_one)

RAW = pathlib.Path("raw_pdfs")
PROCESSED = RAW / "_processed"
API = os.getenv("ON_API", "http://localhost:5055").rstrip("/")
POLL = int(os.getenv("POLL", "4"))


def _get(path):
    with urllib.request.urlopen(f"{API}{path}", timeout=15) as r:
        return json.loads(r.read().decode())


def pick_notebook():
    if os.getenv("ON_NOTEBOOK"):
        nb_id = os.getenv("ON_NOTEBOOK")
    else:
        nbs = [n for n in _get("/api/notebooks") if not n.get("archived")]
        if not nbs:
            raise SystemExit("No notebook found — create one in Open Notebook, or set ON_NOTEBOOK.")
        nb_id = nbs[0]["id"]
    name = next((n["name"] for n in _get("/api/notebooks") if n["id"] == nb_id), nb_id)
    return nb_id, name


def push(notebook_id, title, content):
    data = urllib.parse.urlencode({
        "notebook_id": notebook_id, "type": "text", "content": content,
        "title": title, "embed": "true", "async_processing": "true",
    }).encode()
    req = urllib.request.Request(
        f"{API}/api/sources", data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def main():
    PROCESSED.mkdir(exist_ok=True)
    notebook_id, name = pick_notebook()
    print(f"watching {RAW}/  ->  de-id  ->  notebook '{name}'   (Ctrl-C to stop)", flush=True)
    while True:
        for pdf in sorted(RAW.glob("*.pdf")):
            try:
                print(f"• {pdf.name}: de-identifying…", flush=True)
                info = ingest.process_one(pdf)
                source = push(notebook_id, pdf.stem, info["out"].read_text())
                pdf.rename(PROCESSED / pdf.name)
                print(f"  ✓ {info['pii_removed']} PII removed → pushed to notebook "
                      f"(source {source['id']}); raw moved to _processed/", flush=True)
            except Exception as e:
                print(f"  ✗ {pdf.name} failed: {e} (left in raw_pdfs/ to retry)", flush=True)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
