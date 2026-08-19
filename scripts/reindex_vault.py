#!/usr/bin/env python3
"""Re-index the Obsidian vault into Odysseus's RAG store (ChromaDB).

Run inside the odysseus container:
    docker exec odysseus-odysseus-1 python /app/data/reindex_vault.py

Idempotent: clears the vault's prior chunks first, then re-indexes .md/.txt
only (so .obsidian/.git config never pollutes retrieval). Safe to re-run
whenever the notes change.
"""
import json
import os
import sys

sys.path.insert(0, "/app")
from src.rag_manager import RAGManager

# Override to index one vault at a time, e.g.
#   docker exec -e VAULT_PATH=/app/data/personal_docs/obsidian/brain \
#     odysseus-odysseus-1 python /app/data/reindex_vault.py
# remove_directory() and index_personal_documents() are both path-scoped, so a
# per-vault run clears and rebuilds only that subtree.
VAULT = os.getenv("VAULT_PATH", "/app/data/personal_docs/obsidian")
EXTS = {".md", ".txt"}
AUTH_FILE = "/app/data/auth.json"


def resolve_owner():
    """Chat retrieval filters RAG by owner == username, so chunks must be
    tagged with the owner. Auto-detect from auth.json (single-user installs);
    override with OWNER env var if needed."""
    env = os.getenv("OWNER", "").strip()
    if env:
        return env
    try:
        with open(AUTH_FILE) as f:
            users = list(json.load(f).get("users", {}).keys())
        if len(users) == 1:
            return users[0]
    except Exception:
        pass
    return "admin"


def main():
    owner = resolve_owner()
    print(f"owner = {owner}")
    rag = RAGManager()
    try:
        removed = rag.vector_rag.remove_directory(VAULT)
        print(f"cleared prior chunks: {removed}")
    except Exception as e:
        print(f"(clear skipped: {e})")
    res = rag.index_personal_documents(VAULT, file_extensions=EXTS, owner=owner)
    print("index result:", res)
    print("stats:", rag.get_stats())


if __name__ == "__main__":
    main()
