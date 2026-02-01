"""Prompt module handler for loading and executing prompts."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..connectors.types import Conversation
from ..providers.types import AgentConfig, Message, MessageRole


@dataclass
class PromptDefinition:
    """Definition of a prompt module."""

    name: str
    description: str = ""
    category: str = "analysis"
    parameters: dict[str, Any] = field(default_factory=dict)
    system_prompt: str = ""
    output_format: str = ""
    examples: str = ""

    def to_agent_config(self, model: str | None = None) -> AgentConfig:
        """Convert to AgentConfig for provider."""
        return AgentConfig(
            model=model,  # None means use provider's default
            system_prompt=self.system_prompt,
            max_turns=1,
            temperature=0.7,
            max_tokens=4096,
        )


@dataclass
class PromptResult:
    """Result of executing a prompt."""

    prompt_name: str
    raw_output: str
    parsed_output: dict[str, Any] | None = None
    success: bool = True
    error: str | None = None


class PromptHandler:
    """Handles loading and executing prompt modules."""

    def __init__(self, prompts_dir: Path):
        self.prompts_dir = prompts_dir
        self._prompts: dict[str, PromptDefinition] = {}

    def load_all_prompts(self) -> list[PromptDefinition]:
        """Load all prompt definitions from the prompts directory."""
        self._prompts.clear()

        if not self.prompts_dir.exists():
            return []

        for md_file in self.prompts_dir.glob("*.md"):
            try:
                prompt = self._parse_prompt_file(md_file)
                self._prompts[prompt.name] = prompt
            except Exception:
                continue

        return list(self._prompts.values())

    def get_prompt(self, name: str) -> PromptDefinition | None:
        """Get a prompt by name."""
        if not self._prompts:
            self.load_all_prompts()
        return self._prompts.get(name)

    def _parse_prompt_file(self, filepath: Path) -> PromptDefinition:
        """Parse a prompt markdown file."""
        content = filepath.read_text()
        sections = self._split_sections(content)

        # Extract name from first header
        name = filepath.stem
        for line in content.split("\n"):
            if line.startswith("# "):
                name = line[2:].strip().lower().replace(" ", "-")
                break

        return PromptDefinition(
            name=name,
            description=sections.get("Description", "").strip(),
            category=sections.get("Category", "analysis").strip(),
            parameters=self._parse_parameters(sections.get("Parameters", "")),
            system_prompt=sections.get("System Prompt", "").strip(),
            output_format=sections.get("Output Format", "").strip(),
            examples=sections.get("Examples", "").strip(),
        )

    def _split_sections(self, content: str) -> dict[str, str]:
        """Split markdown content into sections."""
        sections: dict[str, str] = {}
        current_section = ""
        current_content: list[str] = []

        for line in content.split("\n"):
            if line.startswith("## "):
                if current_section:
                    sections[current_section] = "\n".join(current_content)
                current_section = line[3:].strip()
                current_content = []
            else:
                current_content.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_content)

        return sections

    def _parse_parameters(self, content: str) -> dict[str, Any]:
        """Parse parameters from markdown list."""
        params: dict[str, Any] = {}

        for line in content.split("\n"):
            match = re.match(r"^-\s+(\w+):\s*(.+?)(?:\s*\(.*\))?$", line)
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()
                params[key] = self._parse_value(value)

        return params

    def _parse_value(self, value: str) -> Any:
        """Parse a string value into appropriate type."""
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    def render_prompt(
        self,
        prompt: PromptDefinition,
        conversations: list[Conversation],
    ) -> str:
        """
        Render a prompt with conversation context.

        Args:
            prompt: The prompt definition
            conversations: Conversations to analyze

        Returns:
            Rendered prompt string
        """
        # Build conversation summary
        conv_summaries: list[str] = []
        for conv in conversations:
            human_msgs = [m for m in conv.messages if m.role.value == "human"]
            assistant_msgs = [m for m in conv.messages if m.role.value == "assistant"]

            summary = f"""
Session: {conv.session_id}
Started: {conv.started_at.isoformat()}
Human messages: {len(human_msgs)}
Assistant messages: {len(assistant_msgs)}

User messages:
"""
            for msg in human_msgs[:20]:  # Limit to first 20 human messages
                content = msg.content if msg.content else ""
                # Ensure content is a string
                if not isinstance(content, str):
                    content = str(content)
                content = content[:500]
                summary += f"- {content}\n"

            conv_summaries.append(summary)

        context = "\n---\n".join(conv_summaries)

        # Build the full prompt
        full_prompt = f"""Analyze the following conversations:

{context}

{prompt.output_format}

Please analyze these conversations and provide your findings."""

        return full_prompt

    async def execute(
        self,
        prompt: PromptDefinition,
        conversations: list[Conversation],
        provider: Any,  # AgentProvider
    ) -> PromptResult:
        """
        Execute a prompt against conversations.

        Args:
            prompt: The prompt definition
            conversations: Conversations to analyze
            provider: The agent provider to use

        Returns:
            PromptResult with analysis
        """
        try:
            rendered = self.render_prompt(prompt, conversations)
            config = prompt.to_agent_config()

            messages = [Message(role=MessageRole.USER, content=rendered)]
            response = await provider.query(messages, config, stream=False)

            # Extract text from response
            raw_output = ""
            if hasattr(response, "messages") and response.messages:
                raw_output = response.messages[0].content or ""

            # Try to parse JSON output
            parsed = self._try_parse_json(raw_output)

            return PromptResult(
                prompt_name=prompt.name,
                raw_output=raw_output,
                parsed_output=parsed,
                success=True,
            )

        except Exception as e:
            return PromptResult(
                prompt_name=prompt.name,
                raw_output="",
                success=False,
                error=str(e),
            )

    def _try_parse_json(self, text: str) -> dict[str, Any] | None:
        """Try to extract and parse JSON from text."""
        import json

        # Try to find JSON in the text
        # Look for ```json blocks
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find raw JSON object
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def build_unified_system_prompt(
        self,
        base_prompt: str,
        enabled_prompts: list[str] | None = None,
    ) -> str:
        """
        Build a unified system prompt by concatenating base prompt with enabled prompt modules.

        Args:
            base_prompt: The base system prompt for the agent
            enabled_prompts: List of prompt names to include (None = all loaded)

        Returns:
            Combined system prompt string
        """
        # Load prompts if not already loaded
        if not self._prompts:
            self.load_all_prompts()

        # Start with base prompt
        result = base_prompt.strip()

        # Add enabled prompts
        for name, prompt in self._prompts.items():
            if enabled_prompts is not None and name not in enabled_prompts:
                continue

            # Add a section for this prompt
            section_title = name.replace("-", " ").title()
            result += f"\n\n## {section_title}\n"

            # Add the system prompt content
            if prompt.system_prompt:
                result += f"{prompt.system_prompt}\n"

            # Add examples if available
            if prompt.examples:
                result += f"\n### Examples\n{prompt.examples}\n"

        return result

    def get_prompt_names(self) -> list[str]:
        """Get list of all loaded prompt names."""
        if not self._prompts:
            self.load_all_prompts()
        return list(self._prompts.keys())
