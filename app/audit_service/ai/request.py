from openai import OpenAI
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union
from dotenv import load_dotenv
import argparse
import json
from datetime import datetime
from pathlib import Path
from .schema import AuditInsights
from app.logging_utils import AuditLogger, NullAuditLogger

# -------- constants ------ 
load_dotenv()

client = OpenAI()

MAX_URLS = 100

def _summary_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "what_the_data_shows": {"type": "string"},
            "key_strengths": {"type": "string"},
            "primary_weaknesses": {"type": "string"},
            "high_level_roadmap": {"type": "string"},
        },
        "required": ["what_the_data_shows", "key_strengths", "primary_weaknesses", "high_level_roadmap"],
    }


def _per_url_schema() -> Dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "url": {"type": "string"},
                "analysis": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "what_the_data_shows": {"type": "string"},
                        "key_strengths": {"type": "string"},
                        "primary_weaknesses": {"type": "string"},
                        "recommendations": {"type": "string"},
                    },
                    "required": ["what_the_data_shows", "key_strengths", "primary_weaknesses", "recommendations"],
                },
            },
            "required": ["url", "analysis"],
        },
    }


def _build_ai_schema(categories: List[str]) -> Dict[str, Any]:
    executive_props: Dict[str, Any] = {}
    per_url_props: Dict[str, Any] = {}
    for category in categories:
        executive_props[category] = _summary_schema()
        per_url_props[category] = _per_url_schema()

    return {
        "name": "audit_insights",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "executive_summaries": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": executive_props,
                    "required": categories,
                },
                "prioritisation_method": {"type": "string"},
                "key_findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "issue": {"type": "string"},
                            "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                            "impact": {"type": "string"},
                            "effort": {"type": "string", "enum": ["Low", "Medium", "High"]},
                            "explanation": {"type": "string"},
                        },
                        "required": ["issue", "priority", "impact", "effort", "explanation"],
                    },
                },
                "per_url_summaries": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": per_url_props,
                    "required": categories,
                },
            },
            "required": ["executive_summaries", "prioritisation_method", "key_findings", "per_url_summaries"],
        },
    }

# ------- helper fucntions -----

def _extract_categories(audit: Dict[str, Any]) -> List[str]:
    lh = audit.get("lighthouse", {}) or {}
    categories_raw = lh.get("categories") or ""
    categories: List[str] = []
    if isinstance(categories_raw, str):
        categories = [c.strip() for c in categories_raw.split(",") if c.strip()]
    elif isinstance(categories_raw, list):
        categories = [str(c).strip() for c in categories_raw if str(c).strip()]
    if not categories:
        categories = ["performance", "seo"]
    return categories

def build_single_prompt(audit: Dict[str, Any]) -> str:
    """
    Create prompt for AI request

    Args: 
        Audit (Dict[str, Any]): lighthouse audit data
    
    Returns: 
        AI prompt
    """
    lh = audit.get("lighthouse", {}) or {}
    wp = lh.get("website_performance_data", {}) or {}
    per_url = lh.get("per_url_performance_data", {}) or {}
    urls = list(per_url.keys())[:MAX_URLS]

    categories = _extract_categories(audit)
    per_url_by_category: Dict[str, Dict[str, Any]] = {category: {} for category in categories}
    for url in urls:
        entry = per_url.get(url, {}) or {}
        for category in categories:
            if entry.get(category):
                per_url_by_category[category][url] = entry.get(category)

    report_labels = ", ".join(categories)
    payload = {
        "context": {
            "audience": "Business owners and technical leads",
            "purpose": f"Summarise {report_labels} plus provide a prioritised implementation roadmap and per-URL improvement notes.",
            "constraints": [
                "Use only the provided metrics. Do not invent measurements.",
                "Be specific: mention what is good, what is bad, and how to fix it.",
                "Priorities must be explainable and consistent.",
                f"Write executive summaries for: {report_labels}, using the required structure.",
                "Per-URL summaries must be split by topic and use only that topic's metrics.",
                "Do not mention other topics in a per-URL summary.",
                "Use these exact executive summary sections: What the data shows, Key strengths, Primary weaknesses, High level roadmap.",
                "Use these exact per-URL sections: What the data shows, Key strengths, Primary weaknesses, Recommendations.",
                "Format sections using simple HTML tags: <b>Heading</b> and <br/> line breaks.",
                "Use simple HTML tags supported by ReportLab: <b>Heading</b> and <br/> line breaks.",
                "Bullet points should be prefixed with '- ' and separated by <br/>.",
                "Return valid JSON only, matching the schema exactly."
            ]
        },
        "site_averages": wp,
        "per_url_metrics_by_category": per_url_by_category,
        "schema": _build_ai_schema(categories)["schema"]
    }

    return (
        "You are a senior web performance consultant.\n"
        "Analyse the following Lighthouse-derived dataset.\n"
        f"Create executive summaries for: {report_labels}.\n"
        "Use these sections for executive summaries: What the data shows, Key strengths, Primary weaknesses, High level roadmap.\n"
        f"Create per-URL summaries split by category: {report_labels}.\n"
        "Use these sections for per-URL summaries: What the data shows, Key strengths, Primary weaknesses, Recommendations.\n"
        "For each category, use only the per_url_metrics_by_category[category] data.\n"
        "Do not mix topics in per-URL summaries.\n"
        "Each section must be detailed, specific to the findings, and professionally formatted with headings and bullet points.\n"
        "Use only ASCII characters and simple HTML tags (<b> for headings, <br/> for line breaks).\n"
        "Separate the sections with empty lines (<br/><br/>).\n"
        "Return ONLY valid JSON matching the schema provided.\n\n"
        f"DATASET_JSON={json.dumps(payload, ensure_ascii=False)}"
    )

def load_input_file(input_file):
    with open(input_file, "r", encoding="utf-8") as f:
        audit = json.load(f)

    return audit

# ----- main AI request -------

def call_openai(audit: Dict[str, Any], logger: AuditLogger | NullAuditLogger | None = None):
    """
    Creates a requests to openai using the gpt-5.2 model. 
    inputs context from the lighthouse audit and a json schema for the output.

    prompts the AI for executive summary, key findings and per url summaries.

    Args: 
        Audit (Dict[str, Any]): lighthouse audit data
    
    Returns: 
        AI summary data
    """
    active_logger = logger or NullAuditLogger()

    if not audit:
        active_logger.warning("AI summary skipped: no audit provided.")

    categories = _extract_categories(audit)
    prompt = build_single_prompt(audit)

    try:
        response = client.chat.completions.parse(
            model="gpt-5.2",
            messages=[
                {"role": "system", "content": "You are a senior web performance consultant. Analyze the provided website performance data for a lighthouse automation program and follow the instructions to provide an appropriate output."},
                {"role": "user","content": prompt}
            ],
            response_format=AuditInsights,
        )
        parsed = response.choices[0].message.parsed

        per_url_map: Dict[str, Dict[str, Any]] = {
            "performance": {item.url: item.analysis for item in parsed.per_url_summaries.performance},
            "seo": {item.url: item.analysis for item in parsed.per_url_summaries.seo},
        }
        if "accessibility" in categories and parsed.per_url_summaries.accessibility:
            per_url_map["accessibility"] = {
                item.url: item.analysis for item in parsed.per_url_summaries.accessibility
            }
        data_for_pdf = parsed.model_dump()
        data_for_pdf["per_url_summaries"] = {
            category: {k: v.model_dump() for k, v in per_url_map[category].items()}
            for category in per_url_map
        }

        return data_for_pdf 

    except json.JSONDecodeError as e:
        active_logger.error("AI did not return valid JSON.")
        active_logger.error(
            "AI raw output preview",
            preview=response.output_text[:1000] if "response" in locals() else "",
        )
        return None

    except Exception as e:
        active_logger.exception("AI summary request failed.", e)
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input-file",
        required=True,
        help="AI prompt file"
    )

    args = parser.parse_args()

    audit = load_input_file(args.input_file)
    
    # AI request 
    output = call_openai(audit)
