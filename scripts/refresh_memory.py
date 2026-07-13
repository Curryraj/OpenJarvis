"""Refresh the second-brain FAISS store — the write-back loop-closer.

Rebuilds the retrievable memory from two sources:
  1. Curated MARKDOWN from the Obsidian vault: wiki/ + raw/*.md + handoffs/
     (markdown ONLY — never point `memory index` at raw/ or the vault root:
      raw/ is a 600+ file PDF/docx coursework library that pollutes retrieval).
  2. Captured FACTS from the auto-fact service (memory_facts.jsonl) — the
     framework writes these but does NOT retrieve them back, so we fold them
     into FAISS here to close the read/write loop.

Idempotent: clears + rebuilds, so re-running never duplicates (unlike
`jarvis memory index`, which appends). Run after sessions, or on a schedule.

    uv run python scripts/refresh_memory.py
"""
from __future__ import annotations

import json
from pathlib import Path

from openjarvis.core.config import load_config
from openjarvis.tools.storage.faiss_backend import FAISSMemory
from openjarvis.tools.storage.ingest import ingest_path
from openjarvis.tools.storage.chunking import ChunkConfig

VAULT = Path(r"C:\Users\jaiyd\Downloads\working-55")
OS_DIR = Path(r"C:\Users\jaiyd\OneDrive\Desktop\OpenJarvis\os")


def curated_markdown() -> list[Path]:
    """Curated knowledge + the team's own workflows/projects, markdown only.

    Indexing os/workflows + os/projects is what lets the CEO/agents actually
    'know' a workflow: paste a .md there, run this refresh, and it becomes
    retrievable context. (Skip _template.md and other _-prefixed helpers.)
    """
    files: list[Path] = []
    files += sorted((VAULT / "wiki").rglob("*.md"))
    files += sorted((VAULT / "raw").rglob("*.md"))       # 8 curated sources, NOT the PDFs
    files += sorted((VAULT / "handoffs").rglob("*.md"))
    for sub in ("workflows", "projects"):
        files += sorted(p for p in (OS_DIR / sub).rglob("*.md")
                        if not p.name.startswith("_"))
    return files


def captured_facts(facts_path: Path) -> list[str]:
    """Durable facts the auto-fact service extracted from conversations."""
    if not facts_path.exists():
        return []
    out: list[str] = []
    for line in facts_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = (rec.get("text") or "").strip()
        if text:
            out.append(text)
    return out


def main() -> None:
    cfg = load_config()
    chunk_cfg = ChunkConfig(chunk_size=512, chunk_overlap=64)
    facts_path = Path(cfg.memory.facts_path)

    mem = FAISSMemory()
    mem.clear()  # wipe index + persisted files, then rebuild from scratch

    # 1. curated markdown
    md_files = curated_markdown()
    md_chunks = 0
    for f in md_files:
        for ch in ingest_path(f, config=chunk_cfg):
            mem.store(ch.content, source=ch.source,
                      metadata={"offset": ch.offset, "index": ch.index})
            md_chunks += 1

    # 2. captured facts (write-back loop-closer)
    facts = captured_facts(facts_path)
    for text in facts:
        mem.store(text, source="memory_fact", metadata={"kind": "captured_fact"})

    mem.save()
    print(f"REFRESHED: {mem.count()} docs = "
          f"{md_chunks} chunks from {len(md_files)} markdown files "
          f"+ {len(facts)} captured facts")


if __name__ == "__main__":
    main()
