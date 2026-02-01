"""Claude Code connector implementation."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import SourceConnector
from .types import (
    Conversation,
    ConversationBatch,
    ConversationMessage,
    MessageRole,
)


class ClaudeCodeConnector(SourceConnector):
    """Connector for extracting conversations from Claude Code sessions."""

    def __init__(self, runtime_dir: Path):
        super().__init__("claude-code")
        self.runtime_dir = runtime_dir
        self._last_processed_file = runtime_dir / "state" / "claude_code_cursor.json"

    @property
    def connector_name(self) -> str:
        return "Claude Code"

    def _get_claude_projects_dir(self) -> Path:
        """Get the Claude Code projects directory."""
        if self.settings.path:
            path = Path(self.settings.path).expanduser()
        else:
            path = Path.home() / ".claude" / "projects"
        return path

    def _parse_message_role(self, role: str) -> MessageRole:
        """Convert Claude Code role to internal role."""
        role_map = {
            "user": MessageRole.HUMAN,
            "human": MessageRole.HUMAN,
            "assistant": MessageRole.ASSISTANT,
            "tool_use": MessageRole.TOOL_CALL,
            "tool_result": MessageRole.TOOL_RESULT,
        }
        return role_map.get(role.lower(), MessageRole.HUMAN)

    def _parse_timestamp(self, ts: Any) -> datetime | None:
        """Parse timestamp from various formats."""
        if ts is None:
            return None
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts)
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    def _extract_text_content(self, data: Any) -> str:
        """Recursively extract text content from various data formats."""
        if data is None:
            return ""
        if isinstance(data, str):
            return data
        if isinstance(data, list):
            text_parts = []
            for item in data:
                extracted = self._extract_text_content(item)
                if extracted:
                    text_parts.append(extracted)
            return "\n".join(text_parts)
        if isinstance(data, dict):
            # If it's a text block, extract the text
            if data.get("type") == "text":
                return data.get("text", "")
            # If it's a tool_result block, extract content
            if data.get("type") == "tool_result":
                return self._extract_text_content(data.get("content", ""))
            # If it looks like a nested message, extract its content
            if "content" in data:
                return self._extract_text_content(data["content"])
            # If it has a text field directly
            if "text" in data:
                return data["text"]
            # For tool use blocks, summarize the tool call
            if data.get("type") == "tool_use":
                tool_name = data.get("name", "unknown")
                return f"[Tool call: {tool_name}]"
        return ""

    def _parse_message(self, msg_data: dict[str, Any]) -> ConversationMessage | None:
        """Parse a single message from Claude Code format."""
        # Handle different message formats
        role_str = msg_data.get("role", msg_data.get("type", ""))
        if not role_str:
            return None

        role = self._parse_message_role(role_str)

        # Extract content using recursive helper
        content = ""
        if "content" in msg_data:
            content = self._extract_text_content(msg_data["content"])
        elif "message" in msg_data:
            content = self._extract_text_content(msg_data["message"])

        timestamp = self._parse_timestamp(
            msg_data.get("timestamp") or msg_data.get("ts")
        )

        # Handle tool-specific fields
        tool_name = None
        tool_input = None
        tool_result = None

        if role == MessageRole.TOOL_CALL:
            tool_name = msg_data.get("name") or msg_data.get("tool_name")
            tool_input = msg_data.get("input") or msg_data.get("tool_input")
        elif role == MessageRole.TOOL_RESULT:
            tool_result = msg_data.get("result") or msg_data.get("output") or content

        return ConversationMessage(
            role=role,
            content=content,
            timestamp=timestamp,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_result=tool_result,
        )

    def _parse_session_file(self, file_path: Path) -> Conversation | None:
        """Parse a single session file into a Conversation."""
        try:
            messages: list[ConversationMessage] = []
            started_at: datetime | None = None
            ended_at: datetime | None = None

            with open(file_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        msg_data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg = self._parse_message(msg_data)
                    if msg:
                        messages.append(msg)
                        if msg.timestamp:
                            if started_at is None or msg.timestamp < started_at:
                                started_at = msg.timestamp
                            if ended_at is None or msg.timestamp > ended_at:
                                ended_at = msg.timestamp

            if not messages:
                return None

            # Use file modification time as fallback
            if started_at is None:
                started_at = datetime.fromtimestamp(file_path.stat().st_mtime)
            if ended_at is None:
                ended_at = datetime.fromtimestamp(file_path.stat().st_mtime)

            # Extract project directory (working directory) from path
            # Path format: ~/.claude/projects/-Users-foo-bar-project/session.jsonl
            # The project dir name is URL-encoded working directory
            project_dir = file_path.parent.name
            working_directory = project_dir.replace("-", "/")  # Decode path separators

            return Conversation(
                session_id=file_path.stem,
                messages=messages,
                started_at=started_at,
                ended_at=ended_at,
                source_type="claude_code",
                metadata={
                    "file_path": str(file_path),
                    "working_directory": working_directory,
                    "project_dir": project_dir,
                },
            )
        except Exception:
            return None

    async def extract_conversations(
        self,
        since: datetime | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> ConversationBatch:
        """Extract conversations from Claude Code sessions."""
        projects_dir = self._get_claude_projects_dir()

        if not projects_dir.exists():
            return ConversationBatch(conversations=[], has_more=False)

        conversations: list[Conversation] = []
        session_files: list[Path] = []

        # Find all JSONL files in project directories
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue

            for jsonl_file in project_dir.glob("*.jsonl"):
                # Filter by modification time if since is provided
                if since:
                    mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime)
                    # Convert since to local naive time for comparison
                    if since.tzinfo:
                        # Convert UTC to local time, then strip tzinfo
                        since_cmp = since.astimezone().replace(tzinfo=None)
                    else:
                        since_cmp = since
                    if mtime < since_cmp:
                        continue
                session_files.append(jsonl_file)

        # Sort by modification time (newest first)
        session_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        # Handle cursor (file path)
        if cursor:
            cursor_path = Path(cursor)
            try:
                idx = session_files.index(cursor_path)
                session_files = session_files[idx + 1 :]
            except ValueError:
                pass

        # Apply limit
        has_more = False
        if limit and len(session_files) > limit:
            session_files = session_files[:limit]
            has_more = True

        # Parse each session file
        for file_path in session_files:
            conv = self._parse_session_file(file_path)
            if conv:
                conversations.append(conv)

        # Set cursor for next batch
        next_cursor = None
        if has_more and session_files:
            next_cursor = str(session_files[-1])

        return ConversationBatch(
            conversations=conversations,
            cursor=next_cursor,
            has_more=has_more,
        )

    async def get_last_processed_timestamp(self) -> datetime | None:
        """Get timestamp of last processed conversation."""
        if not self._last_processed_file.exists():
            return None

        try:
            data = json.loads(self._last_processed_file.read_text())
            ts = data.get("last_processed")
            if ts:
                return datetime.fromisoformat(ts)
        except (json.JSONDecodeError, ValueError):
            pass

        return None

    async def set_last_processed_timestamp(self, timestamp: datetime) -> None:
        """Set timestamp of last processed conversation."""
        self._last_processed_file.parent.mkdir(parents=True, exist_ok=True)

        data = {"last_processed": timestamp.isoformat()}
        self._last_processed_file.write_text(json.dumps(data))
