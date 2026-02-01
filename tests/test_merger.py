"""Tests for report merging and deduplication."""

import pytest

from good_night.dreaming.merger import MergeConfig, ReportMerger, merge_analysis_reports
from good_night.dreaming.report import AnalysisReport, Evidence, Issue, IssueType, Severity


class TestReportMerger:
    """Tests for ReportMerger class."""

    def test_merge_empty_reports(self) -> None:
        """Test merging empty report list."""
        merger = ReportMerger()
        result = merger.merge_reports([])

        assert result.connector_id == "merged"
        assert len(result.issues) == 0

    def test_merge_single_report(self) -> None:
        """Test merging single report returns it unchanged."""
        report = AnalysisReport(
            connector_id="test",
            issues=[Issue(title="Test")],
            conversations_analyzed=5,
        )

        merger = ReportMerger()
        result = merger.merge_reports([report])

        assert result.connector_id == "test"
        assert len(result.issues) == 1

    def test_deduplicate_similar_issues(self) -> None:
        """Test deduplication of similar issues."""
        issues = [
            Issue(
                type=IssueType.REPEATED_REQUEST,
                title="User asks for help with file paths",
                description="User frequently asks about file paths",
            ),
            Issue(
                type=IssueType.REPEATED_REQUEST,
                title="User asks for help with file paths",
                description="User often requests file path assistance",
            ),
        ]

        merger = ReportMerger(MergeConfig(similarity_threshold=0.7))
        deduplicated = merger.deduplicate_issues(issues)

        assert len(deduplicated) == 1

    def test_keep_different_issues(self) -> None:
        """Test that different issues are not merged."""
        issues = [
            Issue(
                type=IssueType.REPEATED_REQUEST,
                title="File path issues",
                description="User has trouble with file paths",
            ),
            Issue(
                type=IssueType.FRUSTRATION_SIGNAL,
                title="User frustrated with output format",
                description="User expresses frustration about formatting",
            ),
        ]

        merger = ReportMerger()
        deduplicated = merger.deduplicate_issues(issues)

        assert len(deduplicated) == 2

    def test_merge_evidence(self) -> None:
        """Test that evidence is merged from similar issues."""
        issues = [
            Issue(
                type=IssueType.REPEATED_REQUEST,
                title="Same issue",
                evidence=[Evidence(session_id="session-1")],
            ),
            Issue(
                type=IssueType.REPEATED_REQUEST,
                title="Same issue",
                evidence=[Evidence(session_id="session-2")],
            ),
        ]

        merger = ReportMerger(MergeConfig(combine_evidence=True))
        deduplicated = merger.deduplicate_issues(issues)

        assert len(deduplicated) == 1
        assert len(deduplicated[0].evidence) == 2

    def test_use_highest_severity(self) -> None:
        """Test that highest severity is used when merging."""
        issues = [
            Issue(
                type=IssueType.REPEATED_REQUEST,
                title="Same issue",
                severity=Severity.LOW,
            ),
            Issue(
                type=IssueType.REPEATED_REQUEST,
                title="Same issue",
                severity=Severity.HIGH,
            ),
        ]

        merger = ReportMerger(MergeConfig(prefer_higher_severity=True))
        deduplicated = merger.deduplicate_issues(issues)

        assert len(deduplicated) == 1
        assert deduplicated[0].severity == Severity.HIGH

    def test_average_confidence(self) -> None:
        """Test that confidence is averaged when merging."""
        issues = [
            Issue(
                type=IssueType.REPEATED_REQUEST,
                title="Same issue",
                confidence=0.6,
            ),
            Issue(
                type=IssueType.REPEATED_REQUEST,
                title="Same issue",
                confidence=0.8,
            ),
        ]

        merger = ReportMerger()
        deduplicated = merger.deduplicate_issues(issues)

        assert len(deduplicated) == 1
        assert deduplicated[0].confidence == 0.7


class TestMergeAnalysisReports:
    """Tests for convenience merge function."""

    def test_merge_multiple_reports(self) -> None:
        """Test merging multiple reports."""
        reports = [
            AnalysisReport(
                connector_id="connector-1",
                issues=[Issue(title="File path configuration problems")],
                conversations_analyzed=5,
            ),
            AnalysisReport(
                connector_id="connector-2",
                issues=[Issue(title="User authentication failures")],
                conversations_analyzed=3,
            ),
        ]

        result = merge_analysis_reports(reports)

        assert result.conversations_analyzed == 8
        assert len(result.issues) == 2
