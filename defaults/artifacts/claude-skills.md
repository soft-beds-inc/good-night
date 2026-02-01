# Claude Skills Artifact

## Description
Creates skill files that Claude Code can use to improve its behavior.

## Settings
- enabled: true
- output_path: ~/.claude/skills/
- scope: global

## File Format
Skills are markdown files with YAML frontmatter:
```markdown
---
name: skill-name
description: What this skill does
version: 1.0.0
generated_by: good-night
---
# Skill Content

## When to Use
[conditions]

## Instructions
[instructions]
```

## Validation Rules
- Must have name in frontmatter
- Must have description section
- Must have instructions section
- Content should be < 500 lines

## For Resolution Agent
When generating this artifact type:
1. Create skill in output_path or project .claude/skills/
2. Use the file format above
3. Keep instructions focused and specific
4. Include practical examples
