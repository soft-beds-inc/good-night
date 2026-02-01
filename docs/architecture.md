# Good Night Architecture

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GOOD NIGHT                                      │
│                    AI Conversation Analysis & Learning                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA SOURCES                                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │  Claude Code    │  │    Future:      │  │    Future:      │              │
│  │  Conversations  │  │    Cursor       │  │    Other IDEs   │              │
│  │                 │  │                 │  │                 │              │
│  │ ~/.claude/      │  │                 │  │                 │              │
│  │   projects/     │  │                 │  │                 │              │
│  └────────┬────────┘  └─────────────────┘  └─────────────────┘              │
└───────────┼─────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DREAMING PIPELINE                                    │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        STEP 1: ANALYSIS                               │   │
│  │                     (Agentic Detection)                               │   │
│  │                                                                       │   │
│  │   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐          │   │
│  │   │ Agent 1 │    │ Agent 2 │    │ Agent 3 │    │ Agent N │          │   │
│  │   │Project A│    │Project B│    │Project C│    │Project N│          │   │
│  │   └────┬────┘    └────┬────┘    └────┬────┘    └────┬────┘          │   │
│  │        │              │              │              │                 │   │
│  │        └──────────────┴──────────────┴──────────────┘                 │   │
│  │                              │                                        │   │
│  │                    Tools Available:                                   │   │
│  │        • list_conversations  • get_messages (paginated)              │   │
│  │        • search_messages     • get_full_message                      │   │
│  │        • scan_recent_human_messages  • report_issue                  │   │
│  │                              │                                        │   │
│  │                              ▼                                        │   │
│  │                    ┌─────────────────┐                               │   │
│  │                    │  Raw Issues     │                               │   │
│  │                    │  (Cast wide net)│                               │   │
│  │                    └────────┬────────┘                               │   │
│  └─────────────────────────────┼────────────────────────────────────────┘   │
│                                │                                             │
│                                ▼                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                       STEP 2: COMPARISON                              │   │
│  │                     (Agentic Filtering)                               │   │
│  │                                                                       │   │
│  │   ┌─────────────────────────────────────────────────────────────┐    │   │
│  │   │                    Comparison Agent                          │    │   │
│  │   │                                                              │    │   │
│  │   │  For each issue:                                            │    │   │
│  │   │    1. Search Redis for similar past resolutions             │    │   │
│  │   │    2. Calculate similarity score                            │    │   │
│  │   │    3. Decide: INCLUDE or EXCLUDE                           │    │   │
│  │   │                                                              │    │   │
│  │   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │    │   │
│  │   │  │ score > 0.85│  │ 0.6 - 0.85 │  │ score < 0.6 │         │    │   │
│  │   │  │   RESOLVED  │  │  RECURRING  │  │     NEW     │         │    │   │
│  │   │  │   (skip)    │  │  (include)  │  │  (include)  │         │    │   │
│  │   │  └─────────────┘  └─────────────┘  └─────────────┘         │    │   │
│  │   └─────────────────────────────────────────────────────────────┘    │   │
│  │                              │                                        │   │
│  │                    Tools Available:                                   │   │
│  │        • get_current_issues    • get_issue_details                   │   │
│  │        • compare_issue_to_resolutions (Redis vector search)          │   │
│  │        • include_issue         • exclude_issue                       │   │
│  │                              │                                        │   │
│  │                              ▼                                        │   │
│  │                    ┌─────────────────┐                               │   │
│  │                    │ Filtered Issues │                               │   │
│  │                    │ (Signal, not    │                               │   │
│  │                    │  noise)         │                               │   │
│  │                    └────────┬────────┘                               │   │
│  └─────────────────────────────┼────────────────────────────────────────┘   │
│                                │                                             │
│                                ▼                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      STEP 3: RESOLUTION                               │   │
│  │                    (Agentic Generation)                               │   │
│  │                                                                       │   │
│  │   ┌─────────────────────────────────────────────────────────────┐    │   │
│  │   │                   Resolution Agent                           │    │   │
│  │   │                                                              │    │   │
│  │   │  1. Review filtered issues                                  │    │   │
│  │   │  2. Check available artifact types                          │    │   │
│  │   │  3. Create resolution actions                               │    │   │
│  │   │  4. Finalize and validate                                   │    │   │
│  │   └─────────────────────────────────────────────────────────────┘    │   │
│  │                              │                                        │   │
│  │                    Tools Available:                                   │   │
│  │        • get_issues_to_resolve   • get_artifact_types                │   │
│  │        • create_resolution_action • list_pending_actions             │   │
│  │        • finalize_resolution                                         │   │
│  │                              │                                        │   │
│  │                              ▼                                        │   │
│  │              ┌───────────────┴───────────────┐                       │   │
│  │              │                               │                       │   │
│  │              ▼                               ▼                       │   │
│  │   ┌─────────────────┐             ┌─────────────────┐               │   │
│  │   │  Claude Skills  │             │   CLAUDE.md     │               │   │
│  │   │ ~/.claude/skills│             │   (per project) │               │   │
│  │   └─────────────────┘             └─────────────────┘               │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Storage Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STORAGE LAYER                                      │
│                                                                              │
│  ┌─────────────────────────────┐    ┌─────────────────────────────────────┐ │
│  │        Redis                │    │         File System                  │ │
│  │   (Vector Store)            │    │                                      │ │
│  │                             │    │  ~/.good-night/                      │ │
│  │  ┌───────────────────────┐  │    │  ├── config.yaml                    │ │
│  │  │  Resolution Vectors   │  │    │  ├── state.json                     │ │
│  │  │                       │  │    │  ├── resolutions/                   │ │
│  │  │  • 384-dim embeddings │  │    │  │   └── *.json                     │ │
│  │  │  • Cosine similarity  │  │    │  ├── artifacts/                     │ │
│  │  │  • KNN search         │  │    │  │   ├── claude-skills.md           │ │
│  │  │                       │  │    │  │   └── claude-md.md               │ │
│  │  └───────────────────────┘  │    │  └── prompts/                       │ │
│  │                             │    │      ├── pattern-detection.md       │ │
│  │  Model: all-MiniLM-L6-v2   │    │      └── frustration-signals.md     │ │
│  │                             │    │                                      │ │
│  └─────────────────────────────┘    └─────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Observability Stack

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WEIGHTS & BIASES WEAVE                                    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         AUTO-TRACING                                     ││
│  │                                                                          ││
│  │   Every LLM call is automatically traced:                               ││
│  │   • Anthropic API calls                                                 ││
│  │   • AWS Bedrock calls                                                   ││
│  │   • Token usage & latency                                               ││
│  │   • Input/Output content                                                ││
│  │                                                                          ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                      LLM JUDGE SCORERS                                   ││
│  │                                                                          ││
│  │   After Step 3, each resolution is evaluated:                           ││
│  │                                                                          ││
│  │   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐      ││
│  │   │  PII/Secret │ │ Significance│ │Applicability│ │ Local vs    │      ││
│  │   │  Detection  │ │   Score     │ │   Score     │ │   Global    │      ││
│  │   │             │ │             │ │             │ │             │      ││
│  │   │ Detect API  │ │ Is this     │ │ Does this   │ │ Should this │      ││
│  │   │ keys, PII,  │ │ significant │ │ actually    │ │ be project- │      ││
│  │   │ secrets     │ │ enough?     │ │ solve the   │ │ specific or │      ││
│  │   │             │ │             │ │ issue?      │ │ global?     │      ││
│  │   └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘      ││
│  │                                                                          ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                      ONLINE MONITORS                                     ││
│  │                                                                          ││
│  │   PIIDetectionScorer can be configured as a guardrail:                  ││
│  │                                                                          ││
│  │   response, call = my_llm_function.call(prompt)                         ││
│  │   result = await call.apply_scorer(PIIDetectionScorer())                ││
│  │   if result.result["flagged"]:                                          ││
│  │       return "Content blocked"                                          ││
│  │                                                                          ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Complete Data Flow

```
                              ┌─────────────────┐
                              │   User works    │
                              │  with Claude    │
                              │     Code        │
                              └────────┬────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │  Conversations  │
                              │    stored in    │
                              │ ~/.claude/      │
                              │   projects/     │
                              └────────┬────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
                    ▼                  ▼                  ▼
            ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
            │   Project A  │  │   Project B  │  │   Project N  │
            │   Analysis   │  │   Analysis   │  │   Analysis   │
            │    Agent     │  │    Agent     │  │    Agent     │
            └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
                   │                 │                 │
                   │    PARALLEL     │                 │
                   │   EXECUTION     │                 │
                   └────────┬────────┴────────┬────────┘
                            │                 │
                            ▼                 ▼
                     ┌─────────────────────────────┐
                     │      All Reported Issues    │
                     │         (251 found)         │
                     └─────────────┬───────────────┘
                                   │
                                   ▼
                     ┌─────────────────────────────┐
                     │     Comparison Agent        │
                     │                             │
                     │  ┌───────────────────────┐  │
                     │  │    Redis Vector       │  │
                     │  │      Search           │◄─┼──── Historical
                     │  │                       │  │      Resolutions
                     │  └───────────────────────┘  │
                     │                             │
                     │  Include: 33 issues         │
                     │  Exclude: 218 issues        │
                     └─────────────┬───────────────┘
                                   │
                                   ▼
                     ┌─────────────────────────────┐
                     │     Resolution Agent        │
                     │                             │
                     │  Creates artifacts:         │
                     │  • 3 Claude Skills          │
                     │  • 13 Project CLAUDE.md     │
                     └─────────────┬───────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                    ▼              ▼              ▼
          ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
          │   Weave     │  │   Redis     │  │   Output    │
          │ Evaluation  │  │   Store     │  │  Artifacts  │
          │             │  │ (for next   │  │             │
          │ • PII check │  │   cycle)    │  │ • Skills    │
          │ • Scores    │  │             │  │ • CLAUDE.md │
          └─────────────┘  └─────────────┘  └─────────────┘
                                   │
                                   │
                                   ▼
                     ┌─────────────────────────────┐
                     │    Next Dreaming Cycle      │
                     │    uses stored resolutions  │
                     │    to detect recurring vs   │
                     │    already-resolved issues  │
                     └─────────────────────────────┘
```

## Issue Types Detected

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ISSUE CATEGORIES                                    │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │ REPEATED        │  │ FRUSTRATION     │  │ STYLE           │              │
│  │ REQUEST         │  │ SIGNAL          │  │ MISMATCH        │              │
│  │                 │  │                 │  │                 │              │
│  │ User asks for   │  │ User shows      │  │ AI response     │              │
│  │ same thing      │  │ annoyance,      │  │ style doesn't   │              │
│  │ multiple times  │  │ uses profanity, │  │ match user's    │              │
│  │                 │  │ corrects AI     │  │ expectations    │              │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘              │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐                                   │
│  │ CAPABILITY      │  │ KNOWLEDGE       │                                   │
│  │ GAP             │  │ GAP             │                                   │
│  │                 │  │                 │                                   │
│  │ AI can't do     │  │ AI lacks        │                                   │
│  │ what user       │  │ expected        │                                   │
│  │ expects         │  │ knowledge       │                                   │
│  │                 │  │                 │                                   │
│  └─────────────────┘  └─────────────────┘                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Artifact Types Generated

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          OUTPUT ARTIFACTS                                    │
│                                                                              │
│  ┌─────────────────────────────────────┐  ┌─────────────────────────────────┐
│  │         CLAUDE SKILLS               │  │         CLAUDE.md               │
│  │                                     │  │                                 │
│  │  Location: ~/.claude/skills/        │  │  Location: <project>/.claude/   │
│  │                                     │  │            CLAUDE.md            │
│  │  Purpose:                           │  │                                 │
│  │  • Reusable behaviors               │  │  Purpose:                       │
│  │  • Can be invoked with /skill-name  │  │  • Project-specific preferences │
│  │  • Global across all projects       │  │  • Context for that codebase    │
│  │                                     │  │  • Local to one project         │
│  │  Examples:                          │  │                                 │
│  │  • restart-app-after-changes        │  │  Examples:                      │
│  │  • use-devtools-mcp-for-frontend    │  │  • "Use markdown for briefings" │
│  │  • confirm-before-bulk-operations   │  │  • "Never use LIMIT in SQL"     │
│  │                                     │  │  • "Always run tests first"     │
│  └─────────────────────────────────────┘  └─────────────────────────────────┘
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```
