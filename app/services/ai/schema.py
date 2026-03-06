""" AI Schema config
"""

from typing import Dict, List, Literal
from pydantic import BaseModel, Field, ConfigDict

class KeyFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issue: str
    priority: Literal["High", "Medium", "Low"]
    impact: str
    effort: Literal["Low", "Medium", "High"]
    explanation: str

class ExecutiveSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    what_the_data_shows: str
    key_strengths: str
    primary_weaknesses: str
    high_level_roadmap: str

class PerUrlSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    what_the_data_shows: str
    key_strengths: str
    primary_weaknesses: str
    recommendations: str

class PerUrlSummaryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(..., description="Fully-qualified URL")
    analysis: PerUrlSummary

class ExecutiveSummaries(BaseModel):
    model_config = ConfigDict(extra="forbid")
    performance: ExecutiveSummary
    seo: ExecutiveSummary
    accessibility: ExecutiveSummary

class PerUrlSummaries(BaseModel):
    model_config = ConfigDict(extra="forbid")
    performance: List[PerUrlSummaryItem]
    seo: List[PerUrlSummaryItem]
    accessibility: List[PerUrlSummaryItem]

class AuditInsights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    executive_summaries: ExecutiveSummaries
    prioritisation_method: str
    key_findings: List[KeyFinding]
    per_url_summaries: PerUrlSummaries
