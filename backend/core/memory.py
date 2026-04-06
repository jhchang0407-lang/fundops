"""
FundOps Memory System — Claude Code-inspired persistent memory.

Stores user corrections, confirmations, and preferences as markdown files.
Memories are injected into all agent prompts so the entire pipeline learns.

Storage: ~/.fundops/memory/
Format: Markdown with YAML-like frontmatter
"""

import datetime
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("fundops.memory")

MEMORY_DIR = Path.home() / ".fundops" / "memory"


@dataclass
class MemoryEntry:
    id: str
    type: str  # "user" | "feedback" | "project"
    content: str
    why: str
    how_to_apply: str
    created: str
    source: str  # "strategy_conversation" | "api" | "manual"
    session_id: Optional[str] = None


class MemoryStore:
    """File-backed memory store with in-memory cache."""

    def __init__(self, memory_dir: Path = MEMORY_DIR):
        self.memory_dir = memory_dir
        self._cache: Optional[list] = None

    def _ensure_dir(self) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def _load_all(self) -> list:
        """Read all .md files from memory_dir, parse frontmatter + body."""
        self._ensure_dir()
        entries = []
        for f in sorted(self.memory_dir.glob("*.md")):
            if f.name == "MEMORY.md":
                continue
            try:
                entry = self._parse_file(f)
                if entry:
                    entries.append(entry)
            except Exception as e:
                log.warning(f"Failed to parse memory file {f.name}: {e}")
        self._cache = entries
        return entries

    def _parse_file(self, path: Path) -> Optional[MemoryEntry]:
        """Parse a memory markdown file with frontmatter."""
        text = path.read_text(encoding="utf-8").strip()
        if not text.startswith("---"):
            return None

        # Split frontmatter from body
        parts = text.split("---", 2)
        if len(parts) < 3:
            return None

        frontmatter_text = parts[1].strip()
        body = parts[2].strip()

        # Parse frontmatter as simple key-value pairs
        meta = {}
        for line in frontmatter_text.splitlines():
            if ": " in line:
                key, val = line.split(": ", 1)
                meta[key.strip()] = val.strip()

        # Parse body: first paragraph is the rule, then Why: and How to apply:
        lines = body.splitlines()
        content_lines = []
        why = ""
        how_to_apply = ""

        for line in lines:
            if line.startswith("Why: "):
                why = line[5:]
            elif line.startswith("How to apply: "):
                how_to_apply = line[14:]
            else:
                content_lines.append(line)

        return MemoryEntry(
            id=path.stem,
            type=meta.get("type", "feedback"),
            content="\n".join(content_lines).strip(),
            why=why,
            how_to_apply=how_to_apply,
            created=meta.get("created", ""),
            source=meta.get("source", "unknown"),
            session_id=meta.get("session_id"),
        )

    def _invalidate_cache(self) -> None:
        self._cache = None

    def _rebuild_index(self) -> None:
        """Regenerate MEMORY.md index file."""
        self._ensure_dir()
        entries = self.get_all()
        lines = ["# FundOps Memory Index\n"]

        by_type = {}
        for e in entries:
            by_type.setdefault(e.type, []).append(e)

        type_labels = {"user": "User Profile", "feedback": "Feedback & Corrections", "project": "Project Decisions"}
        for t in ["user", "feedback", "project"]:
            group = by_type.get(t, [])
            if group:
                lines.append(f"\n## {type_labels.get(t, t)}")
                for e in group:
                    summary = e.content[:80].replace("\n", " ")
                    lines.append(f"- [{e.id}] {summary}")

        index_path = self.memory_dir / "MEMORY.md"
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def get_all(self) -> list:
        if self._cache is not None:
            return self._cache
        return self._load_all()

    def get_by_type(self, memory_type: str) -> list:
        return [e for e in self.get_all() if e.type == memory_type]

    def get_by_id(self, memory_id: str) -> Optional[MemoryEntry]:
        for e in self.get_all():
            if e.id == memory_id:
                return e
        return None

    def save(self, entry: MemoryEntry) -> str:
        """Write a MemoryEntry to disk. Returns the entry ID."""
        self._ensure_dir()

        # Generate ID if not set
        if not entry.id:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            short_id = uuid.uuid4().hex[:6]
            entry.id = f"{entry.type}_{ts}_{short_id}"

        if not entry.created:
            entry.created = datetime.datetime.now().isoformat()

        # Build file content
        content = f"""---
type: {entry.type}
created: {entry.created}
source: {entry.source}
"""
        if entry.session_id:
            content += f"session_id: {entry.session_id}\n"
        content += f"""---

{entry.content}
Why: {entry.why}
How to apply: {entry.how_to_apply}
"""

        path = self.memory_dir / f"{entry.id}.md"
        path.write_text(content, encoding="utf-8")

        self._invalidate_cache()
        self._rebuild_index()

        log.info(f"Saved memory entry: {entry.id} (type={entry.type})")
        return entry.id

    def save_from_extraction(self, memory_updates: list, session_id: str = "") -> list:
        """Convert raw memory_updates from extraction schema and save each one."""
        saved_ids = []
        existing = self.get_all()

        for update in memory_updates:
            rule = update.get("rule", "").strip()
            if not rule:
                continue

            # Simple dedup: skip if any existing memory has very similar content
            duplicate = False
            rule_words = set(rule.lower().split())
            for existing_entry in existing:
                existing_words = set(existing_entry.content.lower().split())
                if rule_words and existing_words:
                    overlap = len(rule_words & existing_words) / max(len(rule_words), len(existing_words))
                    if overlap > 0.7:
                        log.debug(f"Skipping duplicate memory: {rule[:50]}...")
                        duplicate = True
                        break
            if duplicate:
                continue

            entry = MemoryEntry(
                id="",
                type=update.get("type", "feedback"),
                content=rule,
                why=update.get("why", ""),
                how_to_apply=update.get("how_to_apply", ""),
                created=datetime.datetime.now().isoformat(),
                source="strategy_conversation",
                session_id=session_id,
            )
            entry_id = self.save(entry)
            saved_ids.append(entry_id)

        return saved_ids

    def delete(self, memory_id: str) -> bool:
        """Delete a memory file by ID."""
        path = self.memory_dir / f"{memory_id}.md"
        if path.exists():
            path.unlink()
            self._invalidate_cache()
            self._rebuild_index()
            log.info(f"Deleted memory entry: {memory_id}")
            return True
        return False

    def format_for_injection(self) -> str:
        """Format all memories as a text block for agent prompt injection."""
        entries = self.get_all()
        if not entries:
            return ""

        # Cap at 30 most recent entries
        entries = sorted(entries, key=lambda e: e.created, reverse=True)[:30]

        by_type = {}
        for e in entries:
            by_type.setdefault(e.type, []).append(e)

        sections = []
        type_labels = {"user": "Investor Profile", "feedback": "Corrections & Learned Rules", "project": "Standing Decisions"}

        for t in ["user", "feedback", "project"]:
            group = by_type.get(t, [])
            if group:
                lines = [f"## {type_labels.get(t, t)}"]
                for e in group:
                    line = f"- {e.content}"
                    if e.how_to_apply:
                        line += f" (Apply: {e.how_to_apply})"
                    lines.append(line)
                sections.append("\n".join(lines))

        if not sections:
            return ""

        return "<memory>\n" + "\n\n".join(sections) + "\n</memory>"
