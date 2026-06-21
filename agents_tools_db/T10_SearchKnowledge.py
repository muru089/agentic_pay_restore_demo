"""
T10_SearchKnowledge.py — RAG retrieval tool
-------------------------------------------
TOOL TYPE : Knowledge retrieval (no DB connection — opens ChromaDB directly)
CALLED BY : root_agent only (policy/FAQ questions don't need account context)

Embeds the customer's query using the same Gemini text-embedding-004 model
used at index time, queries ChromaDB for the top-3 matching chunks, and
returns them as a single formatted context string for the agent to answer from.

Prerequisites:
    rag_seed.py must be run at least once to populate the ChromaDB collection.
"""

import os
import chromadb
from pathlib import Path
from google import genai
from dotenv import load_dotenv

BASE_DIR           = Path(__file__).parent.parent   # pay_restore_demo/ root
CHROMA_DIR         = BASE_DIR / "knowledge_base" / "chroma_db"
COLLECTION         = "orbit_help"
EMBED_MODEL        = "gemini-embedding-2"
LOW_CONFIDENCE_THRESHOLD = 0.75  # cosine distance 0–2; above this = weak match

load_dotenv(BASE_DIR / ".env")
_genai_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
_chroma       = chromadb.PersistentClient(path=str(CHROMA_DIR))


def T10_SearchKnowledge(query: str) -> str:
    """
    Search the Orbit help center knowledge base for content relevant to the query.
    Returns the top 3 matching passages as a formatted context string.

    Call this for any general question about Orbit's plans, pricing, billing,
    AutoPay, late fees, fee waivers, suspension, data retention, storage limits,
    plan upgrades or downgrades, or cancellation policy — questions that do not
    require looking up a specific customer account.

    Do not call this for account-specific lookups (use T1_GetAccount instead).

    Input:
        query: The customer's question or topic to search (plain text string).

    Returns:
        A string containing the top 3 relevant knowledge base passages,
        each labelled with its source page. Use this content to answer
        the customer. Do not fabricate details not present in the results.
    """
    # Embed the query using the same model used at index time
    result = _genai_client.models.embed_content(
        model=EMBED_MODEL,
        contents=query,
    )
    query_vec = result.embeddings[0].values

    # Retrieve top-3 chunks
    try:
        collection = _chroma.get_collection(COLLECTION)
    except Exception:
        return (
            "Knowledge base is not available (run rag_seed.py first). "
            "Answer from your general training context."
        )

    results = collection.query(
        query_embeddings=[query_vec],
        n_results=3,
        include=["documents", "metadatas", "distances"],
    )

    docs      = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    if not docs:
        return "[NO_MATCH] No results returned from knowledge base."

    # If the best match is a weak signal, flag it so the agent responds gracefully
    # rather than hallucinating from loosely-related content.
    best_distance = distances[0]
    if best_distance > LOW_CONFIDENCE_THRESHOLD:
        return (
            f"[LOW_CONFIDENCE distance={best_distance:.2f}] "
            "The retrieved passages are not a strong match for this question. "
            "Do not answer from this content — use the graceful acknowledgment response instead."
        )

    parts = []
    for i, (doc, meta, dist) in enumerate(zip(docs, metadatas, distances), 1):
        source = meta.get("source", "unknown")
        parts.append(f"[Source {i} — {source} | distance={dist:.2f}]\n{doc}")

    return "\n\n---\n\n".join(parts)
