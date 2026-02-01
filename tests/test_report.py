"""Tests for dreaming report types."""

import pytest

from good_night.dreaming.report import (
    AnalysisReport,
    EnrichedIssue,
    EnrichedReport,
    Evidence,
    HistoricalLink,
    Issue,
    IssueType,
    Severity,
)


class TestIssue:
    """Tests for Issue class."""

    def test_create_issue(self) -> None:
        """Test creating an issue."""
        issue = Issue(
            type=IssueType.REPEATED_REQUEST,
            severity=Severity.HIGH,
            title="Test Issue",
            description="Test description",
            confidence=0.8,
        )

        assert issue.type == IssueType.REPEATED_REQUEST
        assert issue.severity == Severity.HIGH
        assert issue.title == "Test Issue"
        assert issue.confidence == 0.8
        assert issue.id  # Should have auto-generated ID

    def test_issue_to_dict(self) -> None:
        """Test converting issue to dictionary."""
        evidence = Evidence(
            session_id="session-1",
            message_index=5,
            quote="test quote",
        )
        issue = Issue(
            type=IssueType.FRUSTRATION_SIGNAL,
            severity=Severity.MEDIUM,
            title="Test",
            evidence=[evidence],
        )

        data = issue.to_dict()

        assert data["type"] == "frustration_signal"
        assert data["severity"] == "medium"
        assert len(data["evidence"]) == 1
        assert data["evidence"][0]["session_id"] == "session-1"

    def test_issue_from_dict(self) -> None:
        """Test creating issue from dictionary."""
        data = {
            "id": "test-id",
            "type": "repeated_request",
            "severity": "high",
            "title": "Test Issue",
            "description": "Test",
            "evidence": [{"session_id": "s1", "quote": "q1"}],
            "confidence": 0.9,
        }

        issue = Issue.from_dict(data)

        assert issue.id == "test-id"
        assert issue.type == IssueType.REPEATED_REQUEST
        assert issue.severity == Severity.HIGH
        assert len(issue.evidence) == 1


class TestAnalysisReport:
    """Tests for AnalysisReport class."""

    def test_create_report(self) -> None:
        """Test creating an analysis report."""
        issues = [
            Issue(type=IssueType.REPEATED_REQUEST, title="Issue 1"),
            Issue(type=IssueType.FRUSTRATION_SIGNAL, title="Issue 2"),
        ]
        report = AnalysisReport(
            connector_id="claude-code",
            issues=issues,
            conversations_analyzed=10,
            summary="Test summary",
        )

        assert report.connector_id == "claude-code"
        assert len(report.issues) == 2
        assert report.conversations_analyzed == 10

    def test_report_to_dict(self) -> None:
        """Test converting report to dictionary."""
        report = AnalysisReport(
            connector_id="test",
            issues=[Issue(title="Test")],
            conversations_analyzed=5,
        )

        data = report.to_dict()

        assert data["connector_id"] == "test"
        assert len(data["issues"]) == 1
        assert data["conversations_analyzed"] == 5


class TestEnrichedReport:
    """Tests for EnrichedReport class."""

    def test_issue_filtering(self) -> None:
        """Test filtering issues by status."""
        issues = [
            EnrichedIssue(title="New 1", status="new"),
            EnrichedIssue(title="New 2", status="new"),
            EnrichedIssue(title="Recurring", status="recurring"),
            EnrichedIssue(title="Resolved", status="already_resolved"),
        ]
        report = EnrichedReport(
            connector_id="test",
            issues=issues,
        )

        assert len(report.new_issues) == 2
        assert len(report.recurring_issues) == 1
        assert len(report.resolved_issues) == 1

    def test_from_analysis_report(self) -> None:
        """Test creating enriched report from analysis report."""
        analysis = AnalysisReport(
            connector_id="test",
            issues=[Issue(title="Test Issue")],
            conversations_analyzed=5,
        )

        enriched = EnrichedReport.from_analysis_report(analysis)

        assert enriched.connector_id == "test"
        assert len(enriched.issues) == 1
        assert enriched.conversations_analyzed == 5
        assert isinstance(enriched.issues[0], EnrichedIssue)
