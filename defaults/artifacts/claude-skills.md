# Claude Skills Artifact

## Description
Creates skill files that Claude Code can use to improve its behavior.

## Settings
- enabled: true
- output_path: ~/.claude/skills/
- scope: global

## Content Schema
```yaml
required_fields:
  name: string - The skill name (used as directory name)
  description: string - What this skill does
  instructions: string - Step-by-step instructions for executing the skill

optional_fields:
  when_to_use: string - Conditions when this skill should be invoked
  examples: string - Example usages or scenarios

example:
  name: run-tests
  description: Run the project test suite with coverage
  instructions: |
    1. Activate the virtual environment
    2. Run pytest with coverage flags
    3. Generate coverage report
    4. Report any failures
  when_to_use: When the user asks to run tests or validate changes
  examples: |
    User: 'run the tests'
    User: 'check if my changes break anything'

hint: For skills, content must be an object with 'name', 'description', and 'instructions' as required fields. Skills define reusable, procedural instructions for specific tasks.
```

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
