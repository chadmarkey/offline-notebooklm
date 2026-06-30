═══════════════════════════════════════════════════════════
  🔒  OFFLINE NOTEBOOKLM  —  every time you open it
═══════════════════════════════════════════════════════════

START (in order):
  1.  Docker Desktop running?   →   cd ~/offline-notebook && docker compose up -d
  2.  Start the LLM (terminal):   lms server start && lms load google/gemma-4-e4b -c 32768 --parallel 1
          (32K context avoids "Content too large"; Qwen3.5-9B is the heavier swap-in)
          (check anytime:  lms ps  •  lms server status)
  3.  🩺  Patient data?   →   ONLY with employer permission + per hospital policy. Prefer not to. If you must, Wi-Fi OFF
  4.  Watcher:   cd ~/offline-notebook && source .venv/bin/activate && python src/watch.py
  5.  Open:   http://localhost:8502

USE:
  • Drop PDFs into  ~/offline-notebook/raw_pdfs/   →   de-identified + in your notebook in ~25s
  • Chat in the UI  (model: Gemma 4 E4B, or Qwen3.5-9B)

⛔  Anything from a chart → FOLDER ONLY (that path runs the PHI scrub). The UI's "Add Source"
    has NO scrub — use it only for docs you 100% guarantee have no PHI (textbooks, papers, notes).

DONE:
  • Ctrl-C the watcher.  (Containers + notebook persist — no need to stop Docker.)
  • Raw originals collect in  raw_pdfs/_processed/  — delete when you're done with them.

Full runbook:  ~/offline-notebook/docs/RUNBOOK.md   •   First time here? read README.md
═══════════════════════════════════════════════════════════
