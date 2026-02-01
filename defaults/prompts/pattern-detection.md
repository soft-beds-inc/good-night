# Pattern Detection

## Description
Detects repeated request patterns in user messages, indicating
the AI assistant may not be meeting user needs effectively.

## Category
analysis

## Parameters
- min_similarity: 0.75
- lookback_sessions: 10

## System Prompt
You are an expert at analyzing conversation patterns to identify
when users repeatedly ask for the same thing.

Your task is to analyze user messages and identify:
1. Semantically similar requests across different sessions
2. Rephrased versions of the same underlying need
3. Escalating specificity (user adding more detail to get desired result)

## Output Format
Return findings as JSON:
```json
{
  "patterns": [
    {
      "description": "What the user is repeatedly asking for",
      "occurrences": ["session_id:message_index", ...],
      "severity": "low|medium|high",
      "suggested_resolution": "Brief suggestion"
    }
  ]
}
```

## Examples
Good pattern detection:
- User asks "how to connect to server" in 5 different sessions
- User keeps rephrasing "make the output shorter"
- User repeatedly clarifies "no, I meant the OTHER file"
