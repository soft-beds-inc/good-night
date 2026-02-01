"""LLM Judge Scorers for Weave Evaluation.

Uses Weave's Evaluation system to properly track and aggregate scorer results.
"""

import json
import logging
import os
from typing import Any

import weave

logger = logging.getLogger("good-night.judges")

MAX_INPUT_LENGTH = 8000


def _get_llm_client():
    """Get the appropriate LLM client based on available credentials."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        from anthropic import Anthropic
        return Anthropic(), "claude-sonnet-4-20250514", False

    try:
        import boto3
        session = boto3.Session()
        client = session.client("bedrock-runtime", region_name="us-west-2")
        session.client("sts").get_caller_identity()
        return client, "us.anthropic.claude-sonnet-4-5-20250929-v1:0", True
    except Exception as e:
        logger.warning(f"Bedrock not available: {e}")
        raise RuntimeError("No LLM credentials found.")


@weave.op
def _call_llm(prompt: str, max_tokens: int = 500) -> str:
    """Call LLM using available provider. Traced by Weave."""
    client, model_id, is_bedrock = _get_llm_client()

    if is_bedrock:
        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }),
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"]
    else:
        response = client.messages.create(
            model=model_id,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""


def _truncate(content: str, max_len: int = MAX_INPUT_LENGTH) -> str:
    return content[:max_len] + "..." if len(content) > max_len else content


def _parse_json(text: str, default: dict) -> dict:
    try:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())
    except Exception:
        return default


# Scorers as simple functions decorated with @weave.op
# This integrates properly with Weave's tracing

@weave.op
def score_pii(content: str) -> dict[str, Any]:
    """Detect PII and secrets in resolution content."""
    default = {"has_pii": False, "pii_types": [], "severity": "low", "explanation": ""}
    if not content or not content.strip():
        return {**default, "explanation": "Empty content"}

    prompt = f"""Analyze for PII/secrets:
---
{_truncate(content)}
---
Check for: API keys, passwords, emails, phones, addresses, SSN, credit cards, connection strings.
Severity: high (secrets, SSN), medium (contact info), low (uncertain).
Respond ONLY with JSON: {{"has_pii": bool, "pii_types": [], "severity": "low|medium|high", "explanation": "..."}}"""
    return _parse_json(_call_llm(prompt), default)


@weave.op
def score_significance(resolution_description: str, issue_description: str) -> dict[str, Any]:
    """Judge if a resolution is significant enough to implement."""
    default = {"is_significant": False, "significance_score": 0.0, "rationale": ""}
    if not resolution_description:
        return {**default, "rationale": "No resolution provided"}

    prompt = f"""Evaluate resolution significance:
ISSUE: {_truncate(issue_description, 3000)}
RESOLUTION: {_truncate(resolution_description, 3000)}
Score 0-1: 0-0.3 trivial, 0.4-0.6 moderate, 0.7-0.85 significant, 0.86-1.0 highly significant.
Respond ONLY with JSON: {{"is_significant": bool, "significance_score": 0.0-1.0, "rationale": "..."}}"""
    result = _parse_json(_call_llm(prompt), default)
    if "significance_score" in result:
        result["significance_score"] = max(0.0, min(1.0, float(result["significance_score"])))
        result["is_significant"] = result["significance_score"] >= 0.5
    return result


@weave.op
def score_applicability(
    issue_title: str,
    issue_description: str,
    resolution_content: str | dict,
    resolution_type: str = "",
) -> dict[str, Any]:
    """Check if resolution actually addresses the issue."""
    default = {"is_applicable": False, "coverage_score": 0.0, "gaps": [], "rationale": ""}
    if not issue_title and not issue_description:
        return {**default, "rationale": "No issue provided"}
    if not resolution_content:
        return {**default, "rationale": "No resolution provided"}

    res_str = json.dumps(resolution_content)[:4000] if isinstance(resolution_content, dict) else _truncate(str(resolution_content), 4000)
    prompt = f"""Evaluate if resolution addresses the issue:
ISSUE: {issue_title} - {_truncate(issue_description, 2000)}
TYPE: {resolution_type or "unspecified"}
RESOLUTION: {res_str}
Score 0-1 coverage, list gaps.
Respond ONLY with JSON: {{"is_applicable": bool, "coverage_score": 0.0-1.0, "gaps": [], "rationale": "..."}}"""
    result = _parse_json(_call_llm(prompt, 600), default)
    if "coverage_score" in result:
        result["coverage_score"] = max(0.0, min(1.0, float(result["coverage_score"])))
        result["is_applicable"] = result["coverage_score"] >= 0.5
    if not isinstance(result.get("gaps"), list):
        result["gaps"] = []
    return result


@weave.op
def score_local_vs_global(
    issue_description: str,
    resolution_description: str,
    working_directory: str = "",
) -> dict[str, Any]:
    """Determine if change should be local (project) or global (user-wide)."""
    default = {"should_be_local": False, "confidence": 0.5, "rationale": ""}
    if not issue_description and not resolution_description:
        return {**default, "rationale": "Insufficient info"}

    prompt = f"""Determine if LOCAL (project-specific) or GLOBAL (universal):
ISSUE: {_truncate(issue_description, 2500)}
RESOLUTION: {_truncate(resolution_description, 2500)}
PATH: {working_directory or "Not specified"}
LOCAL: project tech stack, specific files, project conventions.
GLOBAL: universal preferences, general best practices, AI behavior.
Respond ONLY with JSON: {{"should_be_local": bool, "confidence": 0.0-1.0, "rationale": "..."}}"""
    result = _parse_json(_call_llm(prompt, 400), default)
    if "confidence" in result:
        result["confidence"] = max(0.0, min(1.0, float(result["confidence"])))
    return result


@weave.op
def evaluate_resolution_action(
    action_target: str,
    action_content: dict | str,
    action_rationale: str,
    action_type: str,
    action_local_change: bool,
    issue_titles: str,
    issue_descriptions: str,
    working_directory: str = "",
) -> dict[str, Any]:
    """
    Run all scorers on a single resolution action.
    This is the main evaluation function that Weave traces.
    """
    content_str = json.dumps(action_content) if isinstance(action_content, dict) else str(action_content)

    evaluation = {
        "target": action_target,
        "pii": score_pii(content_str),
        "significance": score_significance(action_rationale, issue_descriptions),
        "applicability": score_applicability(
            issue_titles, issue_descriptions, action_content, action_type
        ),
        "local_vs_global": score_local_vs_global(
            issue_descriptions, action_rationale, working_directory
        ),
    }

    # Log warnings for concerning results
    if evaluation["pii"].get("has_pii") and evaluation["pii"].get("severity") == "high":
        logger.warning(f"Resolution {action_target} may contain secrets: {evaluation['pii']}")

    if not evaluation["significance"].get("is_significant", True):
        logger.info(f"Resolution {action_target} has low significance: {evaluation['significance']}")

    if not evaluation["applicability"].get("is_applicable", True):
        logger.warning(f"Resolution {action_target} may not address issues: {evaluation['applicability']}")

    # Check local_change flag consistency
    expected_local = evaluation["local_vs_global"].get("should_be_local", False)
    if action_local_change != expected_local and evaluation["local_vs_global"].get("confidence", 0) > 0.7:
        logger.warning(
            f"Resolution {action_target} local_change={action_local_change} "
            f"but scorer recommends should_be_local={expected_local}"
        )

    return evaluation


async def run_resolution_evaluation(resolution, report) -> dict[str, Any]:
    """
    Run Weave evaluation on all resolution actions.

    Args:
        resolution: Resolution object with actions to evaluate
        report: EnrichedReport with issue details

    Returns:
        Dictionary mapping action targets to evaluation results
    """
    from ..dreaming.report import EnrichedIssue

    # Build issue lookup
    issues_to_resolve = report.new_issues + report.recurring_issues
    issue_map: dict[str, EnrichedIssue] = {issue.id: issue for issue in issues_to_resolve}

    evaluations: dict[str, Any] = {}

    for conn_res in resolution.resolutions:
        for action in conn_res.actions:
            # Get addressed issues
            addressed_issues = [issue_map[ref] for ref in action.issue_refs if ref in issue_map]

            if not addressed_issues:
                logger.warning(f"Resolution {action.target} has no matching issues")
                continue

            issue_titles = ", ".join(i.title for i in addressed_issues)
            issue_descriptions = "\n".join(i.description for i in addressed_issues)

            # Get working directory from evidence
            working_dir = ""
            for issue in addressed_issues:
                if issue.evidence:
                    working_dir = issue.evidence[0].working_directory
                    if working_dir:
                        break

            # Run evaluation (traced by Weave)
            eval_result = evaluate_resolution_action(
                action_target=action.target,
                action_content=action.content,
                action_rationale=action.rationale,
                action_type=action.type,
                action_local_change=action.local_change,
                issue_titles=issue_titles,
                issue_descriptions=issue_descriptions,
                working_directory=working_dir,
            )

            evaluations[action.target] = eval_result

            logger.info(
                f"Evaluated {action.target}: "
                f"pii={eval_result['pii'].get('has_pii', False)}, "
                f"significance={eval_result['significance'].get('significance_score', 'N/A'):.2f}, "
                f"applicability={eval_result['applicability'].get('coverage_score', 'N/A'):.2f}"
            )

    return evaluations
