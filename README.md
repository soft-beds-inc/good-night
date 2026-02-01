# Good Night

An AI reflection system that analyzes conversations and produces artifacts through "dreaming" agents.

## Overview

Good Night is a daemon that runs in the background, analyzing your AI assistant conversations to:

1. **Detect patterns** - Find repeated requests and common frustrations
2. **Compare history** - Check against previous resolutions
3. **Generate solutions** - Create skill files to improve AI behavior

## Installation

```bash
pip install good-night
```

For AWS Bedrock support:
```bash
pip install good-night[bedrock]
```

## Quick Start

```bash
# Start the daemon
good-night start

# Check status
good-night status

# Trigger a dreaming cycle manually
good-night dream

# View logs
good-night logs -f
```

## Configuration

Configuration is stored in `~/.good-night/config.md`. Edit with:

```bash
good-night config edit
```

### Key Settings

```markdown
## Daemon Settings
- poll_interval: 60          # Seconds between checks
- dream_interval: 3600       # Seconds between dream cycles
- log_level: INFO

## Provider Settings
Default provider: anthropic

### Anthropic
- api_key_env: ANTHROPIC_API_KEY
- model: claude-sonnet-4-20250514
```

## Architecture

### Dreaming Pipeline

1. **Step 1: Analysis** - Run prompt modules against new conversations
2. **Step 2: Comparison** - Compare issues with historical resolutions
3. **Step 3: Resolution** - Generate artifacts (skills) to address issues

### Directory Structure

```
~/.good-night/
├── config.md              # Main configuration
├── state.json             # Processing state
├── good-night.pid         # Daemon PID
├── logs/
│   └── daemon.log
├── connectors/            # Connector definitions
│   └── claude-code.md
├── artifacts/             # Artifact definitions
│   └── claude-skills.md
├── prompts/               # Analysis prompts
│   ├── pattern-detection.md
│   └── frustration-signals.md
├── resolutions/           # Generated resolutions
│   └── 2026-01-31-abc123.json
└── output/                # Generated artifacts
    └── skills/
```

## API

When enabled, Good Night exposes a REST API:

```bash
# Get status
curl http://127.0.0.1:7777/api/v1/status

# Trigger dreaming
curl -X POST http://127.0.0.1:7777/api/v1/dream/trigger

# Get history
curl http://127.0.0.1:7777/api/v1/dream/history
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `good-night start` | Start the daemon |
| `good-night stop` | Stop the daemon |
| `good-night status` | Show daemon status |
| `good-night dream` | Trigger dreaming cycle |
| `good-night config` | Manage configuration |
| `good-night logs` | View daemon logs |

## Customization

### Adding Prompts

Create new prompt modules in `~/.good-night/prompts/`:

```markdown
# My Analysis

## Description
Analyze conversations for specific patterns.

## System Prompt
You are an expert at...

## Output Format
Return findings as JSON:
```json
{
  "patterns": [...]
}
```

### Custom Connectors

Connectors define how to extract conversations from sources. Currently supported:

- **claude-code** - Claude Code sessions

## Development

```bash
# Clone and install
git clone https://github.com/good-night/good-night
cd good-night
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check src/
```

## License

MIT
