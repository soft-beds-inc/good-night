# Claude Code Connector

## Description
Extracts conversations from Claude Code sessions.

## Settings
- enabled: true
- path: ~/.claude/projects/
- format: jsonl

## Incremental Processing
Track last processed timestamp per session to avoid re-processing.

## Message Mapping
- user -> human
- assistant -> assistant
- tool_use -> tool_call
- tool_result -> tool_result
