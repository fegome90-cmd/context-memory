"""Domain layer - pure logic, no IO."""

from .events import (
    ContextEvent,
    OperationType,
    EventSource,
    create_read_event,
    create_write_event,
    create_prompt_event,
)
from .parser import (
    parse_jsonl_line,
    serialize_event,
    ParseError,
    InvalidJSONError,
    InvalidEventError,
)
from .pruning import (
    PruningConfig,
    PruneReport,
    prune,
    classify_path,
    dedupe_by_path,
    tag_events,
    sort_by_priority,
    apply_budget,
)
from .plan import (
    PlanAction,
    LoadStep,
    LoadPlan,
    build_load_plan,
    detect_drift,
)

__all__ = [
    # Events
    "ContextEvent",
    "OperationType",
    "EventSource",
    "create_read_event",
    "create_write_event",
    "create_prompt_event",
    # Parser (pure functions only)
    "parse_jsonl_line",
    "serialize_event",
    "ParseError",
    "InvalidJSONError",
    "InvalidEventError",
    # Pruning
    "PruningConfig",
    "PruneReport",
    "prune",
    "classify_path",
    "dedupe_by_path",
    "tag_events",
    "sort_by_priority",
    "apply_budget",
    # Plan
    "PlanAction",
    "LoadStep",
    "LoadPlan",
    "build_load_plan",
    "detect_drift",
]
