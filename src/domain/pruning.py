"""
Pruning strategies for context events.

Implements:
- Tag classification (core, config, test, noise)
- Deduplication by file path
- Priority-based sorting
- Budget enforcement (ops + bytes)
"""

from dataclasses import dataclass
from collections import defaultdict

from .events import ContextEvent, OperationType


# Tag constants
TAG_CORE = "core"
TAG_CONFIG = "config"
TAG_DOC = "doc"
TAG_TEST = "test"
TAG_NOISE = "noise"
TAG_PINNED = "pinned"


@dataclass(frozen=True)
class PruningConfig:
    """Configuration for pruning behavior (immutable)."""
    max_ops: int = 20
    max_bytes_est: int = 120_000  # Estimated bytes budget

    # Path patterns for classification (tuples for immutability)
    core_patterns: tuple[str, ...] = (
        "src/", "lib/", "app/", "api/",
    )
    config_patterns: tuple[str, ...] = (
        "*.json", "*.toml", "*.yaml", "*.yml", "config/", ".env",
    )
    doc_patterns: tuple[str, ...] = (
        "README*", "*.md", "docs/",
    )
    test_patterns: tuple[str, ...] = (
        "tests/", "test_", "_test.py",
    )
    noise_patterns: tuple[str, ...] = (
        "node_modules/", ".venv/", "__pycache__/", ".pytest_cache/",
        "*.pyc", "*.log", "*.tmp", "dist/", "build/", ".git/",
    )

    # Tag priorities (higher = more important)
    # Using tuple of tuples for immutability
    tag_priority: tuple[tuple[str, int], ...] = (
        (TAG_PINNED, 1000),
        (TAG_CONFIG, 100),
        (TAG_CORE, 90),
        (TAG_DOC, 70),
        (TAG_TEST, 50),
        (TAG_NOISE, 10),
    )

    def __post_init__(self):
        """Validate configuration values."""
        if self.max_ops < 0:
            raise ValueError(f"max_ops must be non-negative: {self.max_ops}")
        if self.max_bytes_est < 0:
            raise ValueError(f"max_bytes_est must be non-negative: {self.max_bytes_est}")


def classify_path(path: str, config: PruningConfig) -> set[str]:
    """
    Classify a file path into tags based on patterns.

    Args:
        path: File path to classify
        config: Pruning configuration

    Returns:
        Set of tags (e.g., {"core", "config"})
    """
    tags = set()

    # Check each pattern category (tuples are iterable)
    for pattern in config.noise_patterns:
        if _matches_pattern(path, pattern):
            tags.add(TAG_NOISE)
            return tags  # Noise short-circuits

    for pattern in config.core_patterns:
        if _matches_pattern(path, pattern):
            tags.add(TAG_CORE)

    for pattern in config.config_patterns:
        if _matches_pattern(path, pattern):
            tags.add(TAG_CONFIG)

    for pattern in config.doc_patterns:
        if _matches_pattern(path, pattern):
            tags.add(TAG_DOC)

    for pattern in config.test_patterns:
        if _matches_pattern(path, pattern):
            tags.add(TAG_TEST)

    # If no tags, default to core
    if not tags:
        tags.add(TAG_CORE)

    return tags


def _matches_pattern(path: str, pattern: str) -> bool:
    """Check if path matches a pattern (simple glob-like)."""
    if pattern.endswith("/"):
        return path.startswith(pattern)
    if "*" in pattern:
        import fnmatch
        return fnmatch.fnmatch(path, pattern)
    return path == pattern


def dedupe_by_path(events: list[ContextEvent]) -> list[ContextEvent]:
    """
    Deduplicate READ events by file path.

    Keeps the LAST read for each path. WRITE/EDIT events are preserved.

    Args:
        events: Events to dedupe

    Returns:
        Deduplicated events
    """
    # Track last read per path
    last_read: dict[str, ContextEvent] = {}
    other_events: list[ContextEvent] = []

    for event in events:
        if event.operation == OperationType.READ and event.file_path:
            last_read[event.file_path] = event
        else:
            other_events.append(event)

    # Combine: other events + last reads
    result = list(other_events)
    result.extend(last_read.values())

    # Sort by timestamp
    result.sort(key=lambda e: e.ts)

    return result


def tag_events(events: list[ContextEvent], config: PruningConfig) -> list[ContextEvent]:
    """
    Add tags to events based on file path classification.

    Args:
        events: Events to tag
        config: Pruning configuration

    Returns:
        New events with tags in meta
    """
    tagged = []
    for event in events:
        meta = dict(event.meta)

        if event.file_path:
            tags = classify_path(event.file_path, config)
            meta["tags"] = list(tags)
        elif event.operation == OperationType.PROMPT:
            # Prompts are always pinned (high priority)
            meta["tags"] = [TAG_PINNED]

        # Create new event with updated meta
        tagged.append(ContextEvent(
            operation=event.operation,
            ts=event.ts,
            source=event.source,
            file_path=event.file_path,
            tool=event.tool,
            tool_input=event.tool_input,
            prompt=event.prompt,
            sha256=event.sha256,
            meta=meta,
        ))

    return tagged


def sort_by_priority(events: list[ContextEvent], config: PruningConfig) -> list[ContextEvent]:
    """
    Sort events by priority (highest first).

    Priority is determined by:
    1. Tags (from tag_priority)
    2. Timestamp (more recent = higher priority)

    Args:
        events: Events to sort
        config: Pruning configuration

    Returns:
        Sorted events
    """
    # Convert tag_priority tuple to dict for efficient lookup
    tag_priority_dict = dict(config.tag_priority)

    def get_priority(event: ContextEvent) -> float:
        tags = event.meta.get("tags", [])
        # Max priority from any tag
        tag_prios = [tag_priority_dict.get(t, 0) for t in tags]
        tag_prio = max(tag_prios) if tag_prios else 0

        # Add recency boost (events within last hour)
        import time
        age = time.time() - event.ts
        recency_boost = max(0, 10 - (age / 360))  # Decay over hour

        return tag_prio + recency_boost

    # Sort by priority (descending)
    sorted_events = sorted(events, key=get_priority, reverse=True)
    return sorted_events


def apply_budget(
    events: list[ContextEvent],
    config: PruningConfig
) -> list[ContextEvent]:
    """
    Apply budget constraints (ops + bytes).

    Args:
        events: Prioritized events
        config: Pruning configuration

    Returns:
        Events within budget
    """
    result: list[ContextEvent] = []
    total_ops = 0
    total_bytes = 0

    for event in events:
        # Check op budget
        if total_ops >= config.max_ops:
            break

        # Check bytes budget
        est_bytes = event.estimated_bytes
        if total_bytes + est_bytes > config.max_bytes_est:
            break

        result.append(event)
        total_ops += 1
        total_bytes += est_bytes

    return result


@dataclass
class PruneReport:
    """Report of pruning results."""
    original_count: int
    pruned_count: int
    removed_count: int
    removed_reasons: dict[str, int]  # reason -> count
    final_tags: dict[str, int]  # tag -> count
    total_bytes_est: int


def prune(events: list[ContextEvent], config: PruningConfig | None = None) -> tuple[list[ContextEvent], PruneReport]:
    """
    Prune events to fit budget using the full strategy.

    Strategy:
    1. Tag events by path classification
    2. Dedupe reads by path (keep last)
    3. Sort by priority
    4. Apply budget

    Args:
        events: Events to prune
        config: Pruning configuration (default: PruningConfig())

    Returns:
        Tuple of (pruned_events, report)
    """
    if config is None:
        config = PruningConfig()

    original_count = len(events)

    # Step 1: Tag events
    tagged = tag_events(events, config)

    # Step 2: Dedupe by path
    deduped = dedupe_by_path(tagged)

    # Step 3: Sort by priority
    sorted_events = sort_by_priority(deduped, config)

    # Step 4: Apply budget
    pruned = apply_budget(sorted_events, config)

    # Generate report
    removed_count = original_count - len(pruned)

    removed_reasons = {
        "dedupe": original_count - len(deduped),
        "budget": len(deduped) - len(pruned),
    }

    final_tags: dict[str, int] = defaultdict(int)
    total_bytes = 0
    for event in pruned:
        for tag in event.meta.get("tags", []):
            final_tags[tag] += 1
        total_bytes += event.estimated_bytes

    report = PruneReport(
        original_count=original_count,
        pruned_count=len(pruned),
        removed_count=removed_count,
        removed_reasons=removed_reasons,
        final_tags=dict(final_tags),
        total_bytes_est=total_bytes,
    )

    return pruned, report
