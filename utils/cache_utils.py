import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logger import get_logger


_LOG_PATH = Path("agent-checkpoint.log")
_logger = get_logger("agent.cache")


def load_cache() -> List[Dict[str, Any]]:
    """Read agent-checkpoint.log as JSONL. Missing file => empty list."""
    if not _LOG_PATH.exists():
        return []
    out: List[Dict[str, Any]] = []
    with open(_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    out.append(obj)
            except json.JSONDecodeError:
                continue
    return out


def save_checkpoint(entry: Dict[str, Any]) -> None:
    """
    Append one JSON line to agent-checkpoint.log.
    Expected (flexible) format:
      {
        "question": "...",
        "tables_used": [...],
        "answer": "...",
        "timestamp": "...",
        "source_file": "filename.ext"
      }
    """
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)


def _normalize_question(q: str) -> str:
    q = (q or "").lower()
    q = re.sub(r"[^a-z0-9\s]", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


def _word_overlap(a: str, b: str) -> float:
    aw = set(a.split())
    bw = set(b.split())
    if not aw or not bw:
        return 0.0
    return len(aw & bw) / max(1, min(len(aw), len(bw)))


def find_similar_cache(
    question: str,
    cache_entries: List[Dict[str, Any]],
    *,
    source_file: Optional[str] = None,
    overlap_threshold: float = 0.7,
) -> Optional[Dict[str, Any]]:
    """
    Match logic:
    - exact normalized question match OR
    - high word overlap >= threshold
    If source_file is provided, only match entries from same source_file.
    """
    qn = _normalize_question(question)
    if not qn:
        return None

    _logger.info("Checking cache for question")

    for entry in reversed(cache_entries):
        if source_file:
            sf = str(entry.get("source_file") or "")
            if sf and sf != source_file:
                continue

        raw_q = str(entry.get("question") or "")
        eq = _normalize_question(raw_q)
        if not eq:
            continue
        _logger.debug(f"Comparing with cached question: {raw_q!r}")

        if qn == eq:
            _logger.info("Cache match found (exact)")
            return entry

        score = _word_overlap(qn, eq)
        _logger.debug(f"Similarity score: {score:.3f}")
        if score >= overlap_threshold:
            _logger.info("Cache match found (similarity)")
            return entry

    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

