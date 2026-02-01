"""LLM Judge Scorers for the GoodNightApp dreaming system.

Supports both direct Anthropic API and AWS Bedrock.
"""

import json
import logging
import os
from typing import Any

import weave
from weave import Scorer

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


def _call_llm(prompt: str, max_tokens: int = 500) -> str:
    """Call LLM using available provider."""
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


class PIISecretDetector(Scorer):
    """Detects PII and secrets in content."""

    @weave.op
    def score(self, content: str) -> dict[str, Any]:
        default = {"has_pii": False, "pii_types": [], "severity": "low", "explanation": "Error"}
        if not content or not content.strip():
            return {**default, "explanation": "Empty content"}

        try:
            prompt = f"""Analyze for PII/secrets:
---
{_truncate(content)}
---
Check for: API keys, passwords, emails, phones, addresses, SSN, credit cards, connection strings.
Severity: high (secrets, SSN), medium (contact info), low (uncertain).
Respond ONLY with JSON: {{"has_pii": bool, "pii_types": [], "severity": "low|medium|high", "explanation": "..."}}"""
            return _parse_json(_call_llm(prompt), default)
        except Exception as e:
            logger.error(f"PIISecretDetector error: {e}")
            return {**default, "explanation": str(e)}


class ResolutionSignificanceJudge(Scorer):
    """Judges if a resolution is significant."""

    @weave.op
    def score(self, resolution_description: str, issue_description: str, evidence: str = "") -> dict[str, Any]:
        default = {"is_significant": False, "significance_score": 0.0, "rationale": "Error"}
        if not resolution_description:
            return {**default, "rationale": "No resolution provided"}

        try:
            prompt = f"""Evaluate resolution significance:
ISSUE: {_truncate(issue_description, 3000)}
RESOLUTION: {_truncate(resolution_description, 3000)}
EVIDENCE: {_truncate(evidence, 2000) if evidence else "None"}
Score 0-1: 0-0.3 trivial, 0.4-0.6 moderate, 0.7-0.85 significant, 0.86-1.0 highly significant.
Respond ONLY with JSON: {{"is_significant": bool, "significance_score": 0.0-1.0, "rationale": "..."}}"""
            result = _parse_json(_call_llm(prompt), default)
            if "significance_score" in result:
                result["significance_score"] = max(0.0, min(1.0, float(result["significance_score"])))
                result["is_significant"] = result["significance_score"] >= 0.5
            return result
        except Exception as e:
            logger.error(f"ResolutionSignificanceJudge error: {e}")
            return {**default, "rationale": str(e)}


class IssueQualityJudge(Scorer):
    """Evaluates issue quality."""

    @weave.op
    def score(self, issue_title: str, issue_description: str, evidence: list | str, issue_type: str = "") -> dict[str, Any]:
        default = {"is_quality_issue": False, "quality_score": 0.0, "evidence_strength": "weak", "rationale": "Error"}
        if not issue_title and not issue_description:
            return {**default, "rationale": "No issue provided"}

        try:
            evidence_str = json.dumps(evidence)[:3000] if isinstance(evidence, list) else _truncate(str(evidence), 3000)
            prompt = f"""Evaluate issue quality:
TITLE: {issue_title}
TYPE: {issue_type or "unspecified"}
DESCRIPTION: {_truncate(issue_description, 2000)}
EVIDENCE: {evidence_str}
Score 0-1, evidence_strength: weak/moderate/strong.
Respond ONLY with JSON: {{"is_quality_issue": bool, "quality_score": 0.0-1.0, "evidence_strength": "weak|moderate|strong", "rationale": "..."}}"""
            result = _parse_json(_call_llm(prompt), default)
            if "quality_score" in result:
                result["quality_score"] = max(0.0, min(1.0, float(result["quality_score"])))
                result["is_quality_issue"] = result["quality_score"] >= 0.5
            if result.get("evidence_strength") not in ("weak", "moderate", "strong"):
                result["evidence_strength"] = "weak"
            return result
        except Exception as e:
            logger.error(f"IssueQualityJudge error: {e}")
            return {**default, "rationale": str(e)}


class LocalVsGlobalJudge(Scorer):
    """Determines if a change should be local or global."""

    @weave.op
    def score(self, issue_description: str, resolution_description: str, working_directory: str = "", project_context: str = "") -> dict[str, Any]:
        default = {"should_be_local": False, "confidence": 0.5, "rationale": "Error"}
        if not issue_description and not resolution_description:
            return {**default, "rationale": "Insufficient info"}

        try:
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
        except Exception as e:
            logger.error(f"LocalVsGlobalJudge error: {e}")
            return {**default, "rationale": str(e)}


class ResolutionApplicabilityJudge(Scorer):
    """Checks if resolution addresses the issue."""

    @weave.op
    def score(self, issue_title: str, issue_description: str, resolution_content: str | dict, resolution_type: str = "") -> dict[str, Any]:
        default = {"is_applicable": False, "coverage_score": 0.0, "gaps": [], "rationale": "Error"}
        if not issue_title and not issue_description:
            return {**default, "rationale": "No issue provided"}
        if not resolution_content:
            return {**default, "rationale": "No resolution provided"}

        try:
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
        except Exception as e:
            logger.error(f"ResolutionApplicabilityJudge error: {e}")
            return {**default, "rationale": str(e)}
