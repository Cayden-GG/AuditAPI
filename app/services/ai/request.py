from openai import OpenAI
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union
from dotenv import load_dotenv
import argparse
import argparse
import json
from datetime import datetime
from pathlib import Path
from .schema import AuditInsights

# -------- constants ------ 
load_dotenv()

client = OpenAI()

MAX_URLS = 100

AI_SCHEMA = {
  "name": "audit_insights",
  "schema": {
    "type": "object",
    "additionalProperties": False,
    "properties": {
      "executive_summaries": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
          "performance": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
              "what_the_data_shows": {"type": "string"},
              "key_strengths": {"type": "string"},
              "primary_weaknesses": {"type": "string"},
              "high_level_roadmap": {"type": "string"}
            },
            "required": ["what_the_data_shows", "key_strengths", "primary_weaknesses", "high_level_roadmap"]
          },
          "seo": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
              "what_the_data_shows": {"type": "string"},
              "key_strengths": {"type": "string"},
              "primary_weaknesses": {"type": "string"},
              "high_level_roadmap": {"type": "string"}
            },
            "required": ["what_the_data_shows", "key_strengths", "primary_weaknesses", "high_level_roadmap"]
          },
          "accessibility": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
              "what_the_data_shows": {"type": "string"},
              "key_strengths": {"type": "string"},
              "primary_weaknesses": {"type": "string"},
              "high_level_roadmap": {"type": "string"}
            },
            "required": ["what_the_data_shows", "key_strengths", "primary_weaknesses", "high_level_roadmap"]
          }
        },
        "required": ["performance", "seo", "accessibility"]
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
            "explanation": {"type": "string"}
          },
          "required": ["issue", "priority", "impact", "effort", "explanation"]
        }
      },
      "per_url_summaries": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
          "performance": {
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
                    "recommendations": {"type": "string"}
                  },
                  "required": ["what_the_data_shows", "key_strengths", "primary_weaknesses", "recommendations"]
                }
              },
              "required": ["url", "analysis"]
            }
          },
          "seo": {
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
                    "recommendations": {"type": "string"}
                  },
                  "required": ["what_the_data_shows", "key_strengths", "primary_weaknesses", "recommendations"]
                }
              },
              "required": ["url", "analysis"]
            }
          },
          "accessibility": {
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
                    "recommendations": {"type": "string"}
                  },
                  "required": ["what_the_data_shows", "key_strengths", "primary_weaknesses", "recommendations"]
                }
              },
              "required": ["url", "analysis"]
            }
          }
        },
        "required": ["performance", "seo", "accessibility"]
      }
    },
    "required": ["executive_summaries", "prioritisation_method", "key_findings", "per_url_summaries"]
  }
}

# ------- helper fucntions -----

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

    per_url_by_category: Dict[str, Dict[str, Any]] = {
        "performance": {},
        "seo": {},
        "accessibility": {},
    }
    for url in urls:
        entry = per_url.get(url, {}) or {}
        for category in ("performance", "seo", "accessibility"):
            if entry.get(category):
                per_url_by_category[category][url] = entry.get(category)

    payload = {
        "context": {
            "audience": "Business owners and technical leads",
            "purpose": "Summarise performance, SEO, and accessibility plus provide a prioritised implementation roadmap and per-URL improvement notes.",
            "constraints": [
                "Use only the provided metrics. Do not invent measurements.",
                "Be specific: mention what is good, what is bad, and how to fix it.",
                "Priorities must be explainable and consistent.",
                "Write three executive summaries (performance, seo, accessibility) using the required structure.",
                "Per-URL summaries must be split by topic and use only that topic's metrics.",
                "Do not mention other topics in a per-URL summary (e.g., no SEO notes in performance).",
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
        "schema": AI_SCHEMA["schema"]
    }

    return (
        "You are a senior web performance consultant.\n"
        "Analyse the following Lighthouse-derived dataset.\n"
        "Create three executive summaries: performance, seo, and accessibility.\n"
        "Use these sections for executive summaries: What the data shows, Key strengths, Primary weaknesses, High level roadmap.\n"
        "Create per-URL summaries split by category: performance, seo, accessibility.\n"
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

def call_openai(audit: Dict[str, Any]): 
    """
    Creates a requests to openai using the gpt-5.2 model. 
    inputs context from the lighthouse audit and a json schema for the output.

    prompts the AI for executive summary, key findings and per url summaries.

    Args: 
        Audit (Dict[str, Any]): lighthouse audit data
    
    Returns: 
        AI summary data
    """
    if not audit:
        print("No audit provided for the ai summary.")

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
            "accessibility": {item.url: item.analysis for item in parsed.per_url_summaries.accessibility},
        }
        data_for_pdf = parsed.model_dump()
        data_for_pdf["per_url_summaries"] = {
            category: {k: v.model_dump() for k, v in per_url_map[category].items()}
            for category in per_url_map
        }

        return data_for_pdf 

    except json.JSONDecodeError as e:
        print("AI did not return valid JSON.")
        print("Raw output:", response.output_text[:1000] if "response" in locals() else "")
        return None

    except Exception as e:
        print(f"Error: {e}")
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
