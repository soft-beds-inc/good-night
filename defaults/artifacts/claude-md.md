# CLAUDE.md Artifact

## Description
Manages CLAUDE.md files which contain project-specific preferences, style choices, and guidance for Claude Code.

CLAUDE.md files are different from skills:
- **CLAUDE.md**: Project-level preferences, coding style, conventions, and context that apply broadly to how Claude should work in this project
- **Skills**: Reusable, procedural instructions for specific tasks that can be invoked on-demand

Use CLAUDE.md for:
- Coding style preferences (naming conventions, formatting)
- Project architecture decisions and patterns to follow
- Team conventions and standards
- Technology preferences and constraints
- Communication style preferences
- Context about the project that Claude should always know

Use Skills instead when:
- Defining step-by-step procedures for specific tasks
- Creating reusable workflows that can be triggered by command
- The instruction is task-specific rather than preference-based

## Settings
- enabled: true
- output_path: ./CLAUDE.md
- scope: project

## Content Schema
```yaml
required_fields:
  preferences: list - List of preference strings or section objects

optional_fields: {}

example:
  preferences:
    - Use type hints for all function parameters and return values
    - Prefer early returns to reduce nesting
    - section: Code Style
      items:
        - Use snake_case for Python functions and variables
        - Prefer explicit imports over star imports
    - section: Testing
      items:
        - Use pytest for all tests
        - Aim for 80% code coverage

hint: For CLAUDE.md, content must have a 'preferences' key containing a list. Items can be strings (added to General section) or objects with 'section' and 'items' keys for organized preferences.
```

## File Format
CLAUDE.md files use markdown with optional sections:
```markdown
# Project Preferences

## Code Style
- Use snake_case for Python functions and variables
- Prefer explicit imports over star imports
- Always include type hints

## Architecture
- Follow hexagonal architecture patterns
- Keep business logic in the domain layer

## Conventions
- All API endpoints should be RESTful
- Use UTC for all timestamps

## Communication
- Be concise in explanations
- Show code examples rather than lengthy descriptions
```

## Validation Rules
- Must be valid markdown
- Should have clear section headers
- Preferences should be actionable and specific
- Content should be < 1000 lines
- Avoid duplicating existing content when appending

## For Resolution Agent
When generating this artifact type:
1. Identify whether the feedback is a preference/style choice (CLAUDE.md) or a procedural instruction (skill)
2. Write preferences as clear, actionable statements
3. Group related preferences under appropriate section headers
4. When appending, check for existing sections and add to them rather than creating duplicates
5. Keep language direct and imperative ("Use X", "Prefer Y", "Always Z")
6. Include rationale only when it helps understanding

Examples of good CLAUDE.md content:
- "Use pytest for all tests, not unittest"
- "Prefer composition over inheritance"
- "Always run type checking before committing"
- "Use early returns to reduce nesting"

Examples that should be skills instead:
- "When deploying, first run tests, then build docker image, then push to registry"
- "To debug performance issues, collect metrics, analyze bottlenecks, then optimize"
