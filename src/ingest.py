#!/usr/bin/env python3
"""raw_pdfs/*.pdf  ->  Docling parse  ->  OpenMed de-id (shift_dates)  ->  disease+oncology NER
->  clean_sources/*.md   (de-identified; safe to hand to Open Notebook).

FRONT-DOOR PHI GATE: de-identification happens here, BEFORE any text is embedded, indexed,
or stored. Only clean_sources/*.md should ever reach Open Notebook. Raw PDFs never leave
raw_pdfs/ and are never sent anywhere.

Verified against openmed 1.6.0 / docling 2.107.0. To go MLX-native on the de-id model,
change PII_MODEL to an MLX-supported family (e.g. OpenMed/privacy-filter-mlx) — one line.
"""
import pathlib
import re
import yaml
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat
import openmed
from phi_rules import post_redact

SRC = pathlib.Path("raw_pdfs")
OUT = pathlib.Path("clean_sources")
OUT.mkdir(exist_ok=True)

PII_MODEL = "OpenMed/OpenMed-PII-QwenMed-XLarge-600M-v1"   # de-id gate (recall: catches org/location)
NER_MODELS = [
    ("disease",  "OpenMed/OpenMed-NER-DiseaseDetect-SuperClinical-434M"),   # clinical disease mentions
    ("oncology", "OpenMed/OpenMed-NER-OncologyDetect-MultiMed-568M"),       # cancer / genes / drugs
]
NER_CONF = 0.5

# Force the PyTorch ("hf") backend: the qwen3 PII model isn't MLX-convertible, so OpenMed's
# default auto-MLX path fails and logs a noisy (harmless) traceback before falling back.
# backend="hf" skips the MLX attempt entirely — identical results, clean output.
_CFG = openmed.OpenMedConfig(backend="hf")

# Born-digital PDFs carry a text layer, so OCR is off (also dodges the broken RapidOCR-torch
# config in this docling build). ponytail: scanned/image-only PDFs would need a working OCR
# engine configured here instead.
_pdf_opts = PdfPipelineOptions()
_pdf_opts.do_ocr = False
converter = DocumentConverter(
    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=_pdf_opts)}
)


def _field(e, name):
    """analyze_text yields EntityPrediction objects (attrs), but tolerate dicts too."""
    return e.get(name) if isinstance(e, dict) else getattr(e, name, None)


# de-id placeholders look like [first_name], [date_time], [age 90+] — strip them before NER
# so the medical NER can't tag the placeholder tokens (e.g. "first_name" as an amino acid).
_PLACEHOLDER = re.compile(r"\[[a-z][a-z0-9_+ ]*\]")


def entity_tags(text):
    """Run both NER passes on de-identified text; merge into {label: [sorted unique spans]}."""
    ner_text = _PLACEHOLDER.sub(" ", text)
    tags = {}
    for _kind, model in NER_MODELS:
        # ponytail: model reloads per call; fine for tens of PDFs. For hundreds, pass a shared
        # openmed.ModelLoader to both calls to avoid reloads.
        res = openmed.analyze_text(ner_text, model_id=model, confidence_threshold=NER_CONF, config=_CFG)
        for e in getattr(res, "entities", res):
            label, span = _field(e, "label"), (_field(e, "text") or "").strip()
            if label and span:
                tags.setdefault(label, set()).add(span)
    return {k: sorted(v) for k, v in sorted(tags.items())}


def process_one(pdf):
    """raw PDF -> Docling parse -> de-id -> rule backstop -> NER -> clean_sources/<stem>.md.
    Returns {out, pii_removed, n_entities}. Shared by the CLI and the watcher (watch.py)."""
    md = converter.convert(str(pdf)).document.export_to_markdown()
    # confidence_threshold=0.5: recall-favoring for a PHI gate. At the default 0.7 a partial
    # hospital name ("Brigham") leaked; 0.5 catches it with no damage to clinical content.
    deid = openmed.deidentify(md, method="shift_dates", model_name=PII_MODEL,
                              confidence_threshold=0.5, use_safety_sweep=True, config=_CFG)
    clean = post_redact(deid.deidentified_text)   # rule backstop: age>89, address units
    tags = entity_tags(clean)
    fm = yaml.safe_dump(
        {"source": pdf.name, "deid_method": "shift_dates",
         "pii_removed": len(deid.pii_entities), "entities": tags},
        sort_keys=False, allow_unicode=True,
    )
    out = OUT / f"{pdf.stem}.md"
    out.write_text(f"---\n{fm}---\n\n{clean}")
    return {"out": out, "pii_removed": len(deid.pii_entities),
            "n_entities": sum(len(v) for v in tags.values())}


def main():
    pdfs = sorted(SRC.glob("*.pdf"))
    if not pdfs:
        print("No PDFs in raw_pdfs/. Drop files there and re-run.")
        return
    for pdf in pdfs:
        info = process_one(pdf)
        print(f"✓ {pdf.name}: {info['pii_removed']} PII removed, "
              f"{info['n_entities']} entities tagged → clean_sources/{pdf.stem}.md")


if __name__ == "__main__":
    main()
