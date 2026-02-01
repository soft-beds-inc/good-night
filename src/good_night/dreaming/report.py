"""Data structures for dreaming reports."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from ..providers.types import TokenUsage


class IssueType(str, Enum):
    """Type of issue detected."""

    REPEATED_REQUEST = "repeated_request"
    FRUSTRATION_SIGNAL = "frustration_signal"
    STYLE_MISMATCH = "style_mismatch"
    CAPABILITY_GAP = "capability_gap"
    KNOWLEDGE_GAP = "knowledge_gap"
    OTHER = "other"


class Severity(str, Enum):
    """Severity level of an issue."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Evidence:
    """Evidence supporting an issue."""

    session_id: str
    message_index: int | None = None
    quote: str = ""
    context: str = ""
    working_directory: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = {
            "session_id": self.session_id,
            "message_index": self.message_index,
            "quote": self.quote,
            "context": self.context,
        }
        if self.working_directory:
            result["working_directory"] = self.working_directory
        return result


@dataclass
class Issue:
    """An issue detected during analysis."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: IssueType = IssueType.OTHER
    severity: Severity = Severity.MEDIUM
    title: str = ""
    description: str = ""
    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 0.5
    suggested_resolution: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    local_change: bool = False  # True if issue is project-specific, False if global

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "evidence": [e.to_dict() for e in self.evidence],
            "confidence": self.confidence,
            "suggested_resolution": self.suggested_resolution,
            "metadata": self.metadata,
            "local_change": self.local_change,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Issue":
        """Create from dictionary."""
        evidence = [
            Evidence(
                session_id=e.get("session_id", ""),
                message_index=e.get("message_index"),
                quote=e.get("quote", ""),
                context=e.get("context", ""),
                working_directory=e.get("working_directory", ""),
            )
            for e in data.get("evidence", [])
        ]

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            type=IssueType(data.get("type", "other")),
            severity=Severity(data.get("severity", "medium")),
            title=data.get("title", ""),
            description=data.get("description", ""),
            evidence=evidence,
            confidence=data.get("confidence", 0.5),
            suggested_resolution=data.get("suggested_resolution", ""),
            metadata=data.get("metadata", {}),
            local_change=data.get("local_change", False),
        )


@dataclass
class AnalysisReport:
    """Report from Step 1 analysis."""

    connector_id: str
    issues: list[Issue] = field(default_factory=list)
    conversations_analyzed: int = 0
    summary: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    token_usage: TokenUsage = field(default_factory=TokenUsage)

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector_id": self.connector_id,
            "issues": [i.to_dict() for i in self.issues],
            "conversations_analyzed": self.conversations_analyzed,
            "summary": self.summary,
            "created_at": self.created_at.isoformat(),
            "token_usage": self.token_usage.to_dict(),
        }


@dataclass
class HistoricalLink:
    """Link to a historical resolution."""

    resolution_id: str
    skill_path: str = ""
    description: str = ""
    relevance_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolution_id": self.resolution_id,
            "skill_path": self.skill_path,
            "description": self.description,
            "relevance_score": self.relevance_score,
        }


@dataclass
class EnrichedIssue(Issue):
    """Issue enriched with historical context."""

    historical_links: list[HistoricalLink] = field(default_factory=list)
    is_recurring: bool = False
    status: str = "new"  # new, recurring, already_resolved

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base["historical_links"] = [h.to_dict() for h in self.historical_links]
        base["is_recurring"] = self.is_recurring
        base["status"] = self.status
        return base

    @classmethod
    def from_issue(cls, issue: Issue) -> "EnrichedIssue":
        """Create EnrichedIssue from Issue."""
        return cls(
            id=issue.id,
            type=issue.type,
            severity=issue.severity,
            title=issue.title,
            description=issue.description,
            evidence=issue.evidence,
            confidence=issue.confidence,
            suggested_resolution=issue.suggested_resolution,
            metadata=issue.metadata,
            local_change=issue.local_change,
        )


@dataclass
class EnrichedReport:
    """Report enriched with historical context."""

    connector_id: str
    issues: list[EnrichedIssue] = field(default_factory=list)
    conversations_analyzed: int = 0
    summary: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    historical_resolutions_checked: int = 0
    token_usage: TokenUsage = field(default_factory=TokenUsage)

    @property
    def new_issues(self) -> list[EnrichedIssue]:
        """Get only new issues."""
        return [i for i in self.issues if i.status == "new"]

    @property
    def recurring_issues(self) -> list[EnrichedIssue]:
        """Get recurring issues."""
        return [i for i in self.issues if i.status == "recurring"]

    @property
    def resolved_issues(self) -> list[EnrichedIssue]:
        """Get already resolved issues."""
        return [i for i in self.issues if i.status == "already_resolved"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector_id": self.connector_id,
            "issues": [i.to_dict() for i in self.issues],
            "conversations_analyzed": self.conversations_analyzed,
            "summary": self.summary,
            "created_at": self.created_at.isoformat(),
            "historical_resolutions_checked": self.historical_resolutions_checked,
        }

    @classmethod
    def from_analysis_report(cls, report: AnalysisReport) -> "EnrichedReport":
        """Create from AnalysisReport."""
        return cls(
            connector_id=report.connector_id,
            issues=[EnrichedIssue.from_issue(i) for i in report.issues],
            conversations_analyzed=report.conversations_analyzed,
            summary=report.summary,
            created_at=report.created_at,
            token_usage=report.token_usage,
        )
