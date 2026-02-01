"""Report deduplication and merging."""

from dataclasses import dataclass
from difflib import SequenceMatcher

from .report import AnalysisReport, Issue


@dataclass
class MergeConfig:
    """Configuration for merging."""

    similarity_threshold: float = 0.7
    combine_evidence: bool = True
    prefer_higher_severity: bool = True


class ReportMerger:
    """Merges and deduplicates analysis reports."""

    def __init__(self, config: MergeConfig | None = None):
        self.config = config or MergeConfig()

    def merge_reports(self, reports: list[AnalysisReport]) -> AnalysisReport:
        """
        Merge multiple reports into a single report.

        Args:
            reports: List of reports to merge

        Returns:
            Merged AnalysisReport
        """
        if not reports:
            return AnalysisReport(connector_id="merged")

        if len(reports) == 1:
            return reports[0]

        # Collect all issues
        all_issues: list[Issue] = []
        for report in reports:
            all_issues.extend(report.issues)

        # Deduplicate issues
        merged_issues = self.deduplicate_issues(all_issues)

        # Calculate totals
        total_conversations = sum(r.conversations_analyzed for r in reports)
        connector_ids = list(set(r.connector_id for r in reports))

        return AnalysisReport(
            connector_id=connector_ids[0] if len(connector_ids) == 1 else "merged",
            issues=merged_issues,
            conversations_analyzed=total_conversations,
            summary=f"Merged {len(reports)} reports with {len(merged_issues)} unique issues",
        )

    def deduplicate_issues(self, issues: list[Issue]) -> list[Issue]:
        """
        Deduplicate a list of issues.

        Args:
            issues: List of issues to deduplicate

        Returns:
            Deduplicated list of issues
        """
        if not issues:
            return []

        # Group similar issues
        groups: list[list[Issue]] = []

        for issue in issues:
            merged = False
            for group in groups:
                if self._are_similar(issue, group[0]):
                    group.append(issue)
                    merged = True
                    break

            if not merged:
                groups.append([issue])

        # Merge each group into a single issue
        return [self._merge_issue_group(group) for group in groups]

    def _are_similar(self, issue1: Issue, issue2: Issue) -> bool:
        """Check if two issues are similar enough to merge."""
        # Must be same type
        if issue1.type != issue2.type:
            return False

        # Compare titles
        title_sim = self._text_similarity(issue1.title, issue2.title)
        if title_sim >= self.config.similarity_threshold:
            return True

        # Compare descriptions
        desc_sim = self._text_similarity(issue1.description, issue2.description)
        if desc_sim >= self.config.similarity_threshold:
            return True

        return False

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings."""
        if not text1 or not text2:
            return 0.0
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

    def _merge_issue_group(self, group: list[Issue]) -> Issue:
        """Merge a group of similar issues into one."""
        if len(group) == 1:
            return group[0]

        # Use the first issue as base
        base = group[0]

        # Combine evidence if configured
        if self.config.combine_evidence:
            all_evidence = []
            seen_sessions = set()
            for issue in group:
                for ev in issue.evidence:
                    if ev.session_id not in seen_sessions:
                        all_evidence.append(ev)
                        seen_sessions.add(ev.session_id)
            base.evidence = all_evidence

        # Use highest severity if configured
        if self.config.prefer_higher_severity:
            severity_order = ["critical", "high", "medium", "low"]
            highest_severity = base.severity
            for issue in group:
                if severity_order.index(issue.severity.value) < severity_order.index(
                    highest_severity.value
                ):
                    highest_severity = issue.severity
            base.severity = highest_severity

        # Average confidence
        avg_confidence = sum(i.confidence for i in group) / len(group)
        base.confidence = avg_confidence

        # Update metadata
        base.metadata["merged_count"] = len(group)
        base.metadata["merged_from"] = [i.id for i in group]

        return base


def merge_analysis_reports(reports: list[AnalysisReport]) -> AnalysisReport:
    """
    Convenience function to merge reports with default config.

    Args:
        reports: List of reports to merge

    Returns:
        Merged AnalysisReport
    """
    merger = ReportMerger()
    return merger.merge_reports(reports)
