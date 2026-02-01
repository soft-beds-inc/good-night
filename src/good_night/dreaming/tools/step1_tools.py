"""Step 1 tools for conversation exploration."""

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from ...connectors.types import Conversation
from ...providers.types import ToolDefinition
from ..report import Evidence, Issue, IssueType, Severity
from .base import ToolBuilder


@dataclass
class Step1Context:
    """Context holding state and tool handlers for Step 1 analysis."""

    conversations: list[Conversation]
    reported_issues: list[Issue] = field(default_factory=list)
    _conv_index: dict[str, Conversation] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Build conversation index and project index."""
        self._conv_index = {c.session_id: c for c in self.conversations}
        # Build project index: working_directory -> list of conversations
        self._project_index: dict[str, list[Conversation]] = {}
        for c in self.conversations:
            wd = c.metadata.get("working_directory", "") if c.metadata else ""
            if wd not in self._project_index:
                self._project_index[wd] = []
            self._project_index[wd].append(c)

    async def list_conversations(self, limit: int = 50, offset: int = 0) -> str:
        """List available conversations with metadata."""
        result = []
        for conv in self.conversations[offset : offset + limit]:
            # Get working_directory from metadata
            working_dir = ""
            if conv.metadata:
                working_dir = conv.metadata.get("working_directory", "")

            result.append({
                "id": conv.session_id,
                "started_at": conv.started_at.isoformat() if conv.started_at else None,
                "ended_at": conv.ended_at.isoformat() if conv.ended_at else None,
                "message_count": len(conv.messages),
                "human_messages": sum(1 for m in conv.messages if m.role.value == "human"),
                "assistant_messages": sum(1 for m in conv.messages if m.role.value == "assistant"),
                "working_directory": working_dir,
            })

        return json.dumps({
            "conversations": result,
            "total": len(self.conversations),
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < len(self.conversations),
        }, indent=2)

    async def get_messages(
        self,
        conversation_id: str,
        offset: int = 0,
        limit: int = 50,
    ) -> str:
        """Get paginated messages from a conversation."""
        conv = self._conv_index.get(conversation_id)
        if not conv:
            return json.dumps({"error": f"Conversation {conversation_id} not found"})

        messages = conv.messages[offset : offset + limit]
        result = []
        for i, msg in enumerate(messages):
            content = msg.content if msg.content else ""
            # Truncate long messages
            truncated = len(content) > 500
            if truncated:
                content = content[:500]

            result.append({
                "index": offset + i,
                "role": msg.role.value,
                "content": content,
                "truncated": truncated,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
            })

        return json.dumps({
            "conversation_id": conversation_id,
            "offset": offset,
            "limit": limit,
            "total_messages": len(conv.messages),
            "messages": result,
            "has_more": offset + limit < len(conv.messages),
        }, indent=2)

    async def get_full_message(
        self,
        conversation_id: str,
        message_index: int,
    ) -> str:
        """Get full content of a specific message (not truncated)."""
        conv = self._conv_index.get(conversation_id)
        if not conv:
            return json.dumps({"error": f"Conversation {conversation_id} not found"})

        if message_index < 0 or message_index >= len(conv.messages):
            return json.dumps({"error": f"Message index {message_index} out of range"})

        msg = conv.messages[message_index]
        return json.dumps({
            "conversation_id": conversation_id,
            "message_index": message_index,
            "role": msg.role.value,
            "content": msg.content or "",
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
            "metadata": msg.metadata,
        }, indent=2)

    async def search_messages(
        self,
        query: str,
        role: str = "any",
        conversation_id: str | None = None,
        limit: int = 50,
    ) -> str:
        """Search for messages containing query."""
        results = []
        query_lower = query.lower()

        for conv in self.conversations:
            if conversation_id and conv.session_id != conversation_id:
                continue

            for i, msg in enumerate(conv.messages):
                if role != "any" and msg.role.value != role:
                    continue

                content = msg.content or ""
                if query_lower in content.lower():
                    # Find the match position and extract context
                    match_pos = content.lower().find(query_lower)
                    start = max(0, match_pos - 50)
                    end = min(len(content), match_pos + len(query) + 50)
                    snippet = content[start:end]
                    if start > 0:
                        snippet = "..." + snippet
                    if end < len(content):
                        snippet = snippet + "..."

                    results.append({
                        "conversation_id": conv.session_id,
                        "message_index": i,
                        "role": msg.role.value,
                        "snippet": snippet,
                        "match_count": content.lower().count(query_lower),
                    })

                    if len(results) >= limit:
                        break

            if len(results) >= limit:
                break

        return json.dumps({
            "query": query,
            "role_filter": role,
            "results": results,
            "total_matches": len(results),
            "truncated": len(results) >= limit,
        }, indent=2)

    async def scan_recent_human_messages(
        self,
        working_directory: str | None = None,
        limit: int = 100,
    ) -> str:
        """
        Fetch recent human messages for quick pattern scanning.

        This is the recommended first step - scan through recent user messages
        to quickly identify recurring patterns before diving into specific conversations.
        """
        # Determine which projects to scan
        if working_directory:
            projects = {working_directory: self._project_index.get(working_directory, [])}
        else:
            projects = self._project_index

        result: dict[str, list[dict[str, Any]]] = {}
        total_collected = 0

        for wd, convs in projects.items():
            if total_collected >= limit:
                break

            project_messages: list[dict[str, Any]] = []

            # Collect human messages from all conversations in this project
            # Sort by timestamp (most recent first) across all conversations
            all_human_msgs: list[tuple[Any, str, int]] = []  # (msg, session_id, index)
            for conv in convs:
                for i, msg in enumerate(conv.messages):
                    if msg.role.value == "human":
                        all_human_msgs.append((msg, conv.session_id, i))

            # Sort by timestamp descending (most recent first)
            # Use message index as fallback if no timestamp
            def sort_key(x: tuple) -> tuple:
                msg, _session_id, idx = x
                if msg.timestamp:
                    # Convert to timestamp float for consistent comparison
                    return (1, msg.timestamp.timestamp())
                else:
                    # No timestamp - use index as secondary sort
                    return (0, idx)

            all_human_msgs.sort(key=sort_key, reverse=True)

            # Take up to limit messages per project
            per_project_limit = min(limit - total_collected, limit // max(1, len(projects)))
            for msg, session_id, msg_idx in all_human_msgs[:per_project_limit]:
                content = msg.content or ""
                # Truncate but keep enough for pattern recognition
                truncated = len(content) > 300
                if truncated:
                    content = content[:300] + "..."

                project_messages.append({
                    "session_id": session_id,
                    "message_index": msg_idx,
                    "content": content,
                    "truncated": truncated,
                    "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                })
                total_collected += 1

                if total_collected >= limit:
                    break

            if project_messages:
                result[wd or "(no project)"] = project_messages

        return json.dumps({
            "projects": result,
            "total_messages": total_collected,
            "total_projects": len(result),
            "hint": "Scan these messages for recurring patterns. Use get_full_message or get_messages to expand context where you see potential issues.",
        }, indent=2)

    async def report_issue(
        self,
        type: str,
        severity: str,
        title: str,
        description: str,
        evidence: list[dict[str, Any]] | None = None,
        suggested_resolution: str | None = None,
        local_change: bool = False,
    ) -> str:
        """Report an issue found in conversations."""
        try:
            issue_type = IssueType(type)
        except ValueError:
            issue_type = IssueType.OTHER

        try:
            issue_severity = Severity(severity)
        except ValueError:
            issue_severity = Severity.MEDIUM

        # Convert evidence, enriching with working_directory from conversation metadata
        evidence_list = []
        for e in evidence or []:
            session_id = e.get("session_id", "")
            working_directory = e.get("working_directory", "")

            # If working_directory not provided, try to get from conversation metadata
            if not working_directory and session_id:
                conv = self._conv_index.get(session_id)
                if conv and conv.metadata:
                    working_directory = conv.metadata.get("working_directory", "")

            evidence_list.append(Evidence(
                session_id=session_id,
                message_index=e.get("message_index"),
                quote=e.get("quote", ""),
                context=e.get("context", ""),
                working_directory=working_directory,
            ))

        issue = Issue(
            id=str(uuid.uuid4()),
            type=issue_type,
            severity=issue_severity,
            title=title,
            description=description,
            evidence=evidence_list,
            confidence=0.8,
            suggested_resolution=suggested_resolution or "",
            local_change=local_change,
        )

        self.reported_issues.append(issue)

        return json.dumps({
            "success": True,
            "issue_id": issue.id,
            "message": f"Issue reported: {title}",
            "total_issues_reported": len(self.reported_issues),
        })


def create_step1_tools(context: Step1Context) -> list[ToolDefinition]:
    """Create tool definitions for Step 1 analysis."""
    return [
        ToolBuilder.create(
            name="scan_recent_human_messages",
            description="RECOMMENDED FIRST STEP: Fetch last ~100 human messages per project for quick pattern scanning. Use this to quickly identify recurring patterns before diving into specific conversations.",
            handler=context.scan_recent_human_messages,
            properties={
                "working_directory": {
                    "type": "string",
                    "description": "Optional: limit to specific project directory. If omitted, scans all projects.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum messages to return across all projects (default: 100)",
                    "default": 100,
                },
            },
        ),
        ToolBuilder.create(
            name="list_conversations",
            description="List all available conversations with metadata (id, date, message counts). Use pagination for large sets.",
            handler=context.list_conversations,
            properties={
                "limit": {
                    "type": "integer",
                    "description": "Maximum conversations to return (default: 50)",
                    "default": 50,
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination (default: 0)",
                    "default": 0,
                },
            },
        ),
        ToolBuilder.create(
            name="get_messages",
            description="Get messages from a conversation with pagination. Messages over 500 chars are truncated.",
            handler=context.get_messages,
            properties={
                "conversation_id": {
                    "type": "string",
                    "description": "ID of the conversation",
                },
                "offset": {
                    "type": "integer",
                    "description": "Start from this message index (default: 0)",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum messages to return (default: 50)",
                    "default": 50,
                },
            },
            required=["conversation_id"],
        ),
        ToolBuilder.create(
            name="get_full_message",
            description="Get the full, untruncated content of a specific message.",
            handler=context.get_full_message,
            properties={
                "conversation_id": {
                    "type": "string",
                    "description": "ID of the conversation",
                },
                "message_index": {
                    "type": "integer",
                    "description": "Index of the message to retrieve",
                },
            },
            required=["conversation_id", "message_index"],
        ),
        ToolBuilder.create(
            name="search_messages",
            description="Search for patterns across conversations. Returns matching messages with context snippets.",
            handler=context.search_messages,
            properties={
                "query": {
                    "type": "string",
                    "description": "Text to search for (case-insensitive)",
                },
                "role": {
                    "type": "string",
                    "enum": ["human", "assistant", "any"],
                    "description": "Filter by message role (default: any)",
                    "default": "any",
                },
                "conversation_id": {
                    "type": "string",
                    "description": "Optional: limit search to specific conversation",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 50)",
                    "default": 50,
                },
            },
            required=["query"],
        ),
        ToolBuilder.create(
            name="report_issue",
            description="Report an issue found in conversations. Include evidence with session_id and message_index.",
            handler=context.report_issue,
            properties={
                "type": {
                    "type": "string",
                    "enum": ["repeated_request", "frustration_signal", "style_mismatch", "capability_gap", "knowledge_gap", "other"],
                    "description": "Type of issue",
                },
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Severity level",
                },
                "title": {
                    "type": "string",
                    "description": "Short title for the issue",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the issue",
                },
                "evidence": {
                    "type": "array",
                    "description": "Evidence from conversations. working_directory will be auto-populated from conversation metadata if not provided.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string", "description": "Conversation session ID"},
                            "message_index": {"type": "integer", "description": "Index of the message in the conversation"},
                            "quote": {"type": "string", "description": "Relevant quote from the message"},
                            "context": {"type": "string", "description": "Additional context about the evidence"},
                            "working_directory": {"type": "string", "description": "Working directory of the conversation (optional, auto-populated)"},
                        },
                    },
                },
                "suggested_resolution": {
                    "type": "string",
                    "description": "Optional suggestion for how to resolve this issue",
                },
                "local_change": {
                    "type": "boolean",
                    "description": "True if issue is PROJECT-SPECIFIC (about this project's tech stack, architecture, conventions). False (default) if GLOBAL (general user preferences, workflow, communication style, infrastructure handling). Even issues appearing in one project should be false if they reflect general preferences.",
                    "default": False,
                },
            },
            required=["type", "severity", "title", "description"],
        ),
    ]
