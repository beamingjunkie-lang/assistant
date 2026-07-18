"""Persistent memory and personal knowledge management (PKM)."""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from config import Config

logger = logging.getLogger(__name__)


class Memory:
    """
    Stores facts, notes, project state, goals, and conversation history.

    Each entry is a dict::

        {
            "id":        str,           # UUID
            "type":      str,           # fact | note | goal | task | project | log
            "content":   str,
            "tags":      list[str],
            "created":   float,         # unix timestamp
            "updated":   float,
            "project":   str | None,
            "metadata":  dict,
        }
    """

    def __init__(self, config: Config):
        self.path = Path(config.memory_path)
        self.max_entries = config.max_memory_entries
        self._entries: list[dict] = []
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path) as f:
                    self._entries = json.load(f)
                logger.debug("Loaded %d memory entries", len(self._entries))
            except Exception as e:
                logger.warning("Failed to load memory: %s", e)
                self._entries = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self._entries, f, indent=2)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def store(
        self,
        content: str,
        entry_type: str = "fact",
        tags: Optional[list[str]] = None,
        project: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Store a new memory entry; returns its ID."""
        now = time.time()
        entry = {
            "id": str(uuid4()),
            "type": entry_type,
            "content": content,
            "tags": tags or [],
            "created": now,
            "updated": now,
            "project": project,
            "metadata": metadata or {},
        }
        self._entries.append(entry)
        # Evict oldest entries if over limit
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]
        self._save()
        logger.debug("Stored memory %s (%s)", entry["id"], entry_type)
        return entry["id"]

    def update(self, entry_id: str, **kwargs: Any) -> bool:
        for entry in self._entries:
            if entry["id"] == entry_id:
                entry.update(kwargs)
                entry["updated"] = time.time()
                self._save()
                return True
        return False

    def delete(self, entry_id: str) -> bool:
        before = len(self._entries)
        self._entries = [e for e in self._entries if e["id"] != entry_id]
        if len(self._entries) < before:
            self._save()
            return True
        return False

    def get(self, entry_id: str) -> Optional[dict]:
        for entry in self._entries:
            if entry["id"] == entry_id:
                return entry
        return None

    # ------------------------------------------------------------------
    # Search / retrieval
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        entry_type: Optional[str] = None,
        tags: Optional[list[str]] = None,
        project: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """Simple keyword search across content."""
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        results = []
        for entry in reversed(self._entries):
            if entry_type and entry["type"] != entry_type:
                continue
            if tags and not all(t in entry["tags"] for t in tags):
                continue
            if project and entry.get("project") != project:
                continue
            if query and not pattern.search(entry["content"]):
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    def recent(self, limit: int = 10, entry_type: Optional[str] = None) -> list[dict]:
        entries = self._entries if not entry_type else [
            e for e in self._entries if e["type"] == entry_type
        ]
        return list(reversed(entries[-limit:]))

    def all_projects(self) -> list[str]:
        return sorted({e["project"] for e in self._entries if e.get("project")})

    def all_tags(self) -> list[str]:
        tags: set[str] = set()
        for entry in self._entries:
            tags.update(entry["tags"])
        return sorted(tags)

    # ------------------------------------------------------------------
    # Knowledge graph helpers
    # ------------------------------------------------------------------

    def link_entries(self, source_id: str, target_id: str, relation: str = "related") -> bool:
        """Record a named relationship between two entries."""
        source = self.get(source_id)
        if not source:
            return False
        links = source.setdefault("metadata", {}).setdefault("links", [])
        links.append({"target": target_id, "relation": relation})
        source["updated"] = time.time()
        self._save()
        return True

    def get_links(self, entry_id: str) -> list[dict]:
        entry = self.get(entry_id)
        if not entry:
            return []
        return entry.get("metadata", {}).get("links", [])

    # ------------------------------------------------------------------
    # Summary helpers
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        types: dict[str, int] = {}
        for e in self._entries:
            types[e["type"]] = types.get(e["type"], 0) + 1
        return {
            "total": len(self._entries),
            "by_type": types,
            "projects": len(self.all_projects()),
            "tags": len(self.all_tags()),
        }

    def format_entry(self, entry: dict) -> str:
        ts = datetime.fromtimestamp(entry["created"]).strftime("%Y-%m-%d %H:%M")
        tags = " ".join(f"#{t}" for t in entry.get("tags", []))
        proj = f"[{entry['project']}]" if entry.get("project") else ""
        parts = [f"[{ts}]", f"({entry['type']})", proj, tags, entry["content"]]
        return " ".join(p for p in parts if p)
