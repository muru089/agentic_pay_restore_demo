"""
rag_seed.py — Orbit knowledge base indexing job
------------------------------------------------
Reads the 6 Orbit help center HTML pages, strips markup, chunks the text,
embeds each chunk via Gemini text-embedding-004, and stores in ChromaDB.

Re-run any time help pages are updated:
    py pay_restore_demo/rag_seed.py   (from c:\\Muru_Workspace)

In production this runs as a nightly scheduled job to pick up
any help page changes made during the day.
"""

import os
import time
import chromadb
from bs4 import BeautifulSoup
from pathlib import Path
from google import genai
from dotenv import load_dotenv

# ── Config ─────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.parent   # pay_restore_demo root (one up from Project Files)
HTML_DIR    = BASE_DIR / "knowledge_base" / "html"
CHROMA_DIR  = BASE_DIR / "knowledge_base" / "chroma_db"
COLLECTION  = "orbit_help"
EMBED_MODEL = "gemini-embedding-2"
CHUNK_CHARS = 2000   # ~500 tokens
OVERLAP_CHARS = 200  # ~50 tokens — ensures context isn't lost at chunk boundaries

# Skip index.html — it's navigation links only, no policy content worth retrieving
PAGES = [
    "plans_pricing.html",
    "billing_payment.html",
    "suspension_reactivation.html",
    "data_retention.html",
    "upgrades_downgrades.html",
    "cancellation.html",
    "diagnostics_integrations.html",
    "team_administration.html",
]

load_dotenv(BASE_DIR / ".env")
_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))


# ── Text extraction ─────────────────────────────────────────────────────────

def extract_text(html_path: Path) -> str:
    """Strip HTML tags and return clean prose text."""
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    for tag in soup.find_all(["nav", "footer", "script", "style"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())


# ── Chunking ────────────────────────────────────────────────────────────────

def chunk_text(text: str, source: str) -> list[dict]:
    """
    Sliding window chunker.
    CHUNK_CHARS window with OVERLAP_CHARS overlap so sentences at boundaries
    appear in two consecutive chunks — prevents a question from falling between
    two chunks and being missed by retrieval.
    """
    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        chunk = text[start : start + CHUNK_CHARS]
        chunks.append({
            "id":          f"{source}__chunk{idx}",
            "text":        chunk,
            "source":      source,
            "chunk_index": idx,
        })
        if start + CHUNK_CHARS >= len(text):
            break
        start += CHUNK_CHARS - OVERLAP_CHARS
        idx += 1
    return chunks


# ── Embedding ───────────────────────────────────────────────────────────────

def embed(text: str) -> list[float]:
    """Embed a single string. Returns 768-dim vector."""
    result = _client.models.embed_content(
        model=EMBED_MODEL,
        contents=text,
    )
    return result.embeddings[0].values


# ── Main ────────────────────────────────────────────────────────────────────

def seed():
    print("=" * 60)
    print("Orbit RAG Seed Job")
    print("=" * 60)

    # Wipe and rebuild for clean full re-index (same as nightly job behavior)
    chroma = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        chroma.delete_collection(COLLECTION)
        print(f"Dropped existing collection '{COLLECTION}' (full re-index)\n")
    except Exception:
        pass
    collection = chroma.create_collection(COLLECTION)

    # Chunk all pages
    all_chunks = []
    for page in PAGES:
        path = HTML_DIR / page
        text = extract_text(path)
        chunks = chunk_text(text, page)
        all_chunks.extend(chunks)
        print(f"  {page}: {len(text):,} chars -> {len(chunks)} chunk(s)")

    print(f"\nEmbedding {len(all_chunks)} chunks via {EMBED_MODEL}...")
    ids, embeddings, documents, metadatas = [], [], [], []

    for i, chunk in enumerate(all_chunks):
        vec = embed(chunk["text"])
        ids.append(chunk["id"])
        embeddings.append(vec)
        documents.append(chunk["text"])
        metadatas.append({"source": chunk["source"], "chunk_index": chunk["chunk_index"]})
        print(f"  [{i+1}/{len(all_chunks)}] {chunk['id']}")
        time.sleep(0.1)  # avoid API rate limiting

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )

    print(f"\n{'='*60}")
    print(f"Done. {len(all_chunks)} chunks stored in ChromaDB.")
    print(f"Location: {CHROMA_DIR}")
    print(f"Collection: '{COLLECTION}'")
    print(f"{'='*60}")


if __name__ == "__main__":
    seed()
