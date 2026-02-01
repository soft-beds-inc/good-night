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

## Running a Dream Cycle

### Basic Usage

```bash
good-night dream
```

On **first run**, you'll be prompted for how many days of conversation history to analyze:

```
First run detected. How many days back should I analyze?
  This determines how much conversation history to process.
  More days = more comprehensive but slower and more expensive.

Days to look back [7]: 30
```

On **subsequent runs**, it automatically processes conversations since the last run.

### Command Flags

| Flag | Description |
|------|-------------|
| `--days`, `-d` | Days to look back (first run only) |
| `--limit`, `-l` | Limit to N conversations (for testing) |
| `--dry-run`, `-n` | Show what would be done without executing |
| `--quiet`, `-q` | Hide real-time agent events |
| `--module`, `-m` | Run specific prompt module only |
| `--connector`, `-c` | Process specific connector only |

### Examples

```bash
# First run: analyze last 30 days
good-night dream --days 30

# Test with just 5 conversations
good-night dream --limit 5

# Dry run (no changes saved)
good-night dream --dry-run

# Silent mode (no live output)
good-night dream --quiet

# Run only pattern-detection prompt
good-night dream --module pattern-detection
```

### How Conversation Selection Works

1. **First run**: Looks back `--days` (or asks interactively, default: 7 days)
2. **Subsequent runs**: Processes all conversations since last run (no limit)
3. **With `--limit`**: Overrides above logic, processes exactly N most recent conversations

Conversations are grouped by project folder, and each folder gets its own analysis agent.

## Configuration

Configuration is stored in `~/.good-night/config.yaml`. Edit with:

```bash
good-night config edit
```

### Key Settings

```yaml
daemon:
  poll_interval: 60          # Seconds between checks
  dream_interval: 3600       # Seconds between dream cycles
  log_level: INFO

provider:
  default: bedrock           # or "anthropic"
  bedrock:
    region: us-east-1
    model: us.anthropic.claude-sonnet-4-5-20250929-v1:0
  anthropic:
    api_key_env: ANTHROPIC_API_KEY
    model: claude-sonnet-4-20250514

enabled:
  connectors:
    - claude-code
  # artifacts: auto-detected from ~/.good-night/artifacts/*.md
  prompts:
    - pattern-detection
    - frustration-signals

dreaming:
  exploration_agents: 1      # Agents per step
  historical_lookback: 7     # Days of history to compare
  initial_lookback_days: 7   # Days for first run (or use --days flag)
```

## Architecture

### Dreaming Pipeline

The dreaming cycle runs in 3 steps:

**Step 1: Detection (Wide Net)**
- Scans conversations for potential issues
- Casts a wide net - reports anything that might be worth improving
- Groups conversations by project folder, runs parallel agents
- Detects: repeated requests, frustrations, style mismatches, capability gaps

**Step 2: Filtering & Comparison**
- Filters Step 1 output to remove noise
- Compares issues with historical resolutions
- Agent decides: include (worth resolving) or exclude (noise)
- Only cross-conversation patterns or significant issues pass through

**Step 3: Resolution Generation**
- Creates artifacts to address included issues
- Outputs: Claude Code skills, CLAUDE.md preferences
- Saves resolutions to `~/.good-night/resolutions/`

### Directory Structure

```
~/.good-night/
├── config.yaml            # Main configuration
├── state.json             # Processing state
├── good-night.pid         # Daemon PID
├── logs/
│   └── daemon.log
├── connectors/            # Connector definitions
│   └── claude-code.md
├── artifacts/             # Artifact definitions (auto-detected)
│   ├── claude-skills.md   # Claude Code skills
│   └── claude-md.md       # CLAUDE.md preferences
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
| `good-night start -f` | Start in foreground (don't daemonize) |
| `good-night stop` | Stop the daemon |
| `good-night stop -f` | Force kill the daemon |
| `good-night status` | Show daemon status |
| `good-night dream` | Trigger dreaming cycle |
| `good-night config show` | Show current configuration |
| `good-night config edit` | Edit configuration in $EDITOR |
| `good-night config reset` | Reset configuration to defaults |
| `good-night logs` | View last 50 log lines |
| `good-night logs -f` | Follow log output |
| `good-night logs -n 100` | View last 100 log lines |

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
