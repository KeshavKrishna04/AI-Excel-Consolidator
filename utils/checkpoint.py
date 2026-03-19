"""
Lightweight checkpointing + caching for agent queries (Consolidated_Sales only).
Append-only log, minimal entries, no large blobs.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

CHECKPOINT_LOG = Path("agent-checkpoint.log")
_KEYWORD_THRESHOLD = 0.6  # overlap ratio to consider similar


def write_checkpoint(entry: Dict[str, Any]) -> None:
    """Append one JSON line to agent-checkpoint.log."""
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    CHECKPOINT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_LOG, "a", encoding="utf-8") as f:
        f.write(line)
    print("[checkpoint] written")


def read_checkpoints() -> List[Dict[str, Any]]:
    """Read file line by line, return list of parsed JSON objects."""
    if not CHECKPOINT_LOG.exists():
        return []
    out: List[Dict[str, Any]] = []
    with open(CHECKPOINT_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _normalize(s: str) -> str:
    """Lowercase, keep alphanumeric and spaces."""
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def find_similar_question(question: str) -> Optional[Dict[str, Any]]:
    """
    Naive similarity: exact lowercase match OR keyword overlap > threshold.
    Returns matching checkpoint entry if found, else None.
    """
    q_norm = _normalize(question)
    if not q_norm:
        return None
    q_words = set(q_norm.split())

    for entry in reversed(read_checkpoints()):
        stored = entry.get("question") or ""
        stored_norm = _normalize(stored)
        if not stored_norm:
            continue
        if q_norm == stored_norm:
            return entry
        stored_words = set(stored_norm.split())
        overlap = len(q_words & stored_words) / max(1, min(len(q_words), len(stored_words)))
        if overlap >= _KEYWORD_THRESHOLD:
            return entry
    return None
