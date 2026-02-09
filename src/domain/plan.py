"""
Load plan builder for context rehydration.

A load plan is a sequence of actions to restore context:
- Read specific files
- Inject user notes/prompts
"""

from dataclasses import dataclass, field
from typing import Literal
from enum import Enum

from .events import ContextEvent


class PlanAction(Enum):
    """Types of actions in a load plan."""
    READ = "read"
    INJECT = "inject"
    WARN = "warn"


@dataclass
class LoadStep:
    """
    A single step in a load plan.

    Steps are executed in order to rebuild context.
    """
    action: PlanAction
    path: str | None = None  # For READ
    content: str | None = None  # For INJECT or WARN
    reason: str = ""  # Why this step exists

    def __str__(self) -> str:
        """Human-readable representation."""
        if self.action == PlanAction.READ:
            return f"📖 Read: {self.path} ({self.reason})"
        elif self.action == PlanAction.INJECT:
            return f"💭 Inject: {self.content[:50]}... ({self.reason})"
        elif self.action == PlanAction.WARN:
            return f"⚠️  Warn: {self.content}"
        return f"{self.action.value}: {self.reason}"


@dataclass
class LoadPlan:
    """
    A complete load plan for rehydration.

    Contains sequence of steps + metadata.
    """
    steps: list[LoadStep] = field(default_factory=list)
    bundle_name: str = ""
    total_files: int = 0
    total_bytes_est: int = 0
    warnings: list[str] = field(default_factory=list)

    def add_read(self, path: str, reason: str = "") -> None:
        """Add a READ step."""
        self.steps.append(LoadStep(
            action=PlanAction.READ,
            path=path,
            reason=reason or f"file: {path}",
        ))
        self.total_files += 1

    def add_inject(self, content: str, reason: str = "") -> None:
        """Add an INJECT step (user note/prompt)."""
        self.steps.append(LoadStep(
            action=PlanAction.INJECT,
            content=content,
            reason=reason or "user intent",
        ))

    def add_warning(self, message: str) -> None:
        """Add a warning."""
        self.warnings.append(message)
        self.steps.append(LoadStep(
            action=PlanAction.WARN,
            content=message,
            reason="warning",
        ))

    def summarize(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"📦 Load Plan: {self.bundle_name or '(unnamed)'}",
            f"   Files to read: {self.total_files}",
            f"   Total steps: {len(self.steps)}",
            f"   Warnings: {len(self.warnings)}",
        ]

        if self.steps:
            lines.append("\n📋 Steps:")
            for i, step in enumerate(self.steps, 1):
                lines.append(f"   {i}. {step}")

        return "\n".join(lines)

    def to_script(self) -> str:
        """
        Generate bash-like script to execute the plan.

        Returns:
            Multi-line string with commands
        """
        lines = ["#!/bin/bash", "# Context Memory Rehydration Script", ""]

        for step in self.steps:
            if step.action == PlanAction.READ:
                lines.append(f"# {step.reason}")
                lines.append(f"echo '→ Reading {step.path}'")
                lines.append(f"cat '{step.path}'")
                lines.append("")
            elif step.action == PlanAction.INJECT:
                lines.append(f"# {step.reason}")
                lines.append(f"echo '→ Note: {step.content[:80]}'")
                lines.append("")
            elif step.action == PlanAction.WARN:
                lines.append(f"echo '⚠️  Warning: {step.content}'")
                lines.append("")

        return "\n".join(lines)


def build_load_plan(events: list[ContextEvent], bundle_name: str = "") -> LoadPlan:
    """
    Build a load plan from pruned events.

    Strategy:
    1. User prompts/notes first (intent)
    2. Config files (context)
    3. Core files (domain logic)
    4. Docs/Tests (support)

    Args:
        events: Pruned events from a bundle
        bundle_name: Name of the bundle

    Returns:
        LoadPlan ready to execute
    """
    plan = LoadPlan(bundle_name=bundle_name)

    # Separate by type
    prompts: list[ContextEvent] = []
    reads: list[ContextEvent] = []
    writes: list[ContextEvent] = []

    for event in events:
        if event.operation.name == "PROMPT":
            prompts.append(event)
        elif event.operation.name == "READ":
            reads.append(event)
        else:
            writes.append(event)

    # 1. User intent first (prompts)
    for event in prompts:
        plan.add_inject(
            content=event.prompt or "",
            reason="user prompt/intent"
        )

    # 2. Group reads by priority (from tags)
    core_reads: list[ContextEvent] = []
    config_reads: list[ContextEvent] = []
    doc_reads: list[ContextEvent] = []
    test_reads: list[ContextEvent] = []
    other_reads: list[ContextEvent] = []

    for event in reads:
        tags = event.meta.get("tags", [])

        if "pinned" in tags or "config" in tags:
            config_reads.append(event)
        elif "core" in tags:
            core_reads.append(event)
        elif "doc" in tags:
            doc_reads.append(event)
        elif "test" in tags:
            test_reads.append(event)
        else:
            other_reads.append(event)

    # 3. Add reads in priority order
    for event in config_reads:
        plan.add_read(
            path=event.file_path or "",
            reason="configuration"
        )

    for event in core_reads:
        plan.add_read(
            path=event.file_path or "",
            reason="core domain"
        )

    for event in doc_reads:
        plan.add_read(
            path=event.file_path or "",
            reason="documentation"
        )

    for event in test_reads:
        plan.add_read(
            path=event.file_path or "",
            reason="tests"
        )

    for event in other_reads:
        plan.add_read(
            path=event.file_path or "",
            reason="other"
        )

    # 4. Warn about writes (files were modified)
    for event in writes:
        if event.file_path:
            plan.add_warning(
                f"File was modified: {event.file_path}"
            )

    return plan


def detect_drift(
    events: list[ContextEvent],
    current_files: dict[str, str]  # path -> current sha256
) -> list[str]:
    """
    Detect drift between bundle and current repo state.

    Args:
        events: Events from bundle (with sha256 in meta)
        current_files: Mapping of path -> current sha256

    Returns:
        List of warning messages
    """
    warnings = []

    for event in events:
        if not event.file_path or not event.sha256:
            continue

        current_sha = current_files.get(event.file_path)
        if not current_sha:
            warnings.append(f"File no longer exists: {event.file_path}")
        elif current_sha != event.sha256:
            warnings.append(
                f"File changed since bundle: {event.file_path}\n"
                f"  Bundle: {event.sha256[:10]}...\n"
                f"  Current: {current_sha[:10]}..."
            )

    return warnings
