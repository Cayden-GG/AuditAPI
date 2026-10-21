"""
Lighthouse audit data normaliser
"""

from typing import Any, Dict, List, Optional, Tuple

from .audit_config import ACCESSIBILITY_AUDIT_IDS, SEO_AUDIT_IDS

SEO_GROUPS: Dict[str, str] = {
    "meta-description": "Metadata",
    "document-title": "Metadata",
    "link-text": "Technical SEO",
    "image-alt": "Technical SEO",
    "robots-txt": "Crawlability",
    "indexing": "Indexability",
    "hreflang": "Metadata",
    "canonical": "Technical SEO",
    "structured-data": "Structured Data",
    "crawlable-anchors": "Crawlability",
    "http-status-code": "Indexability",
    "is-crawlable": "Crawlability",
    "tap-targets": "Mobile Usability",
    "viewport": "Mobile Usability",
    "plugins": "Technical SEO",
    "charset": "Technical SEO",
}

CRITICAL_SEO_AUDITS = {
    "robots-txt",
    "indexing",
    "http-status-code",
    "is-crawlable",
}


def _cw_status(metric: str, value: Optional[float]) -> Optional[str]:
    """Returns a easy clean cut understanding of a metric value"""
    if value is None:
        return None
    
    if metric == "LCP":
        if value <= 2500:
            return "Good"
        if value <= 4000:
            return "Needs Improvement"
        return "Poor"
    
    if metric == "CLS":
        if value <= 0.1:
            return "Good"
        if value <= 0.25:
            return "Needs Improvement"
        return "Poor"
    
    if metric == "INP":
        if value <= 200:
            return "Good"
        if value <= 500:
            return "Needs Improvement"
        return "Poor"
    
    if metric == "FID":
        if value <= 100:
            return "Good"
        if value <= 300:
            return "Needs Improvement"
        return "Poor"
    
    return None


def _severity_for_seo(audit_id: str, manual: bool) -> str:
    """Categorise seo metrics into severity levels for final report"""
    if manual:
        return "advisory"
    
    if audit_id in CRITICAL_SEO_AUDITS:
        return "critical"
    
    if SEO_GROUPS.get(audit_id) in ("Metadata", "Structured Data", "Technical SEO"):
        return "high"
    
    if SEO_GROUPS.get(audit_id) == "Mobile Usability":
        return "moderate"
    
    return "moderate"


def _severity_for_performance(score: Optional[float], cw_status: Optional[str]) -> str:
    """Categorise performance metrics into severity levels for final report"""
    if cw_status == "Poor":
        return "critical"

    if score is not None and score < 0.5:
        return "high"
    
    if cw_status == "Needs Improvement":
        return "moderate"
    
    if score is not None and score < 0.8:
        return "moderate"
    
    return "advisory"

def _severity_for_accessibility(score: Optional[float], manual: bool) -> str:
    """Categorise accessibility metrics into severity levels for final report"""
    if manual:
        return "advisory"
    
    if score == 0:
        return "high"
    
    if score is not None and score < 0.9:
        return "moderate"
    
    return "advisory"

def _category_audit_ids(categories: Dict[str, Any], category_key: str) -> List[str]:
    """Get the audit ids for the passed category"""
    category = categories.get(category_key, {}) if isinstance(categories, dict) else {}
    refs = category.get("auditRefs") or []
    audit_ids = []

    for ref in refs:
        if isinstance(ref, dict):
            audit_id = ref.get("id")
            if audit_id:
                audit_ids.append(audit_id)

    return audit_ids


def _risk_summary(findings_by_severity: Dict[str, int]) -> str:
    """Return a suitable severity level summary"""
    if findings_by_severity.get("critical", 0) > 0:
        return "High risk: critical issues detected that require immediate remediation."
    
    if findings_by_severity.get("high", 0) > 0:
        return "Elevated risk: high-priority issues need near-term remediation."
    
    if findings_by_severity.get("moderate", 0) > 0:
        return "Moderate risk: improvements recommended to reduce exposure."
    
    return "Low risk: only advisory items identified."


def _build_finding(
    category: str,
    title: str,
    description: str,
    severity: str,
    score: Optional[float],
    affected_elements: List[str],
    standard_reference: Dict[str, Optional[str]],
    recommendation: str,
) -> Dict[str, Any]:
    return {
        "category": category,
        "title": title,
        "description": description,
        "severity": severity,
        "score": score,
        "affected_elements": affected_elements,
        "standard_reference": standard_reference,
        "recommendation": recommendation,
    }


def _performance_findings(
    url: str,
    audits: Dict[str, Any],
    categories: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Optional[float]]:
    """
    Collect lighthouse performance audit findings and score

    @Args:
        url (str) -- page url of audit data
        audits (Dict[str, Any]) -- audit data object
        categories (Dict[str, Any]) -- category object
    
    @Returns:
        list of performance audit findings (List) 
        overall performance audit score
    """
    findings: List[Dict[str, Any]] = []
    perf_score = None
    perf_category = categories.get("performance", {})

    if isinstance(perf_category, dict):
        score = perf_category.get("score")
        if isinstance(score, (int, float)):
            perf_score = float(score)

    lcp = audits.get("largest-contentful-paint", {})
    cls = audits.get("cumulative-layout-shift", {})
    inp = audits.get("interaction-to-next-paint", {})
    fid = audits.get("first-input-delay", {})

    inp_value = inp.get("numericValue") if isinstance(inp, dict) else None
    fid_value = fid.get("numericValue") if isinstance(fid, dict) else None

    metrics = [
        ("LCP", lcp.get("numericValue")),
        ("CLS", cls.get("numericValue")),
        ("INP", inp_value),
    ]

    if inp_value is None and fid_value is not None:
        metrics.append(("FID", fid_value))

    for metric, value in metrics:
        if value is None:
            continue

        status = _cw_status(metric, float(value))

        if status and status != "Good":
            severity = _severity_for_performance(perf_score, status)
            findings.append(_build_finding(
                category="performance",
                title=f"{metric} is {status}",
                description=f"{metric} measured {value:.2f} which is {status.lower()} for Core Web Vitals.",
                severity=severity,
                score=None,
                affected_elements=[url],
                standard_reference={"framework": "Core Web Vitals", "code": metric, "level": None},
                recommendation=f"Reduce main-thread work, optimize assets, and improve server response to bring {metric} into the Good range.",
            ))

    if perf_score is not None and perf_score < 0.8:
        severity = _severity_for_performance(perf_score, None)
        findings.append(_build_finding(
            category="performance",
            title="Overall performance score is below target",
            description=f"Lighthouse performance score is {perf_score:.2f}.",
            severity=severity,
            score=perf_score,
            affected_elements=[url],
            standard_reference={"framework": "Core Web Vitals", "code": "Performance Score", "level": None},
            recommendation="Prioritize performance wins that improve Core Web Vitals and reduce blocking time.",
        ))

    return findings, perf_score


def _seo_findings(url: str, audits: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Collect lighthouse seo audit findings and score

    @Args:
        url (str) -- page url of audit data
        audits (Dict[str, Any]) -- audit data object
        categories (Dict[str, Any]) -- category object
    
    @Returns:
        list of seo audit findings (List) 
        overall seo audit score
    """
    findings: List[Dict[str, Any]] = []

    for audit_id in SEO_AUDIT_IDS:
        audit = audits.get(audit_id, {})

        if not isinstance(audit, dict):
            continue

        if audit.get("error") == "missing_audit":
            continue

        score = audit.get("score")
        manual = audit.get("scoreDisplayMode") == "manual"

        if score == 0 or manual:
            severity = _severity_for_seo(audit_id, manual)
            status_note = "Manual review required." if manual else "Automated check failed."
            findings.append(_build_finding(
                category="seo",
                title=audit.get("title") or "SEO issue",
                description=f"{audit.get('description') or ''} {status_note}".strip(),
                severity=severity,
                score=score if isinstance(score, (int, float)) else None,
                affected_elements=[url],
                standard_reference={
                    "framework": "Search Essentials",
                    "code": SEO_GROUPS.get(audit_id, "Technical SEO"),
                    "level": None,
                },
                recommendation="Manual review required." if manual else "Resolve the failing SEO check and verify with a follow-up crawl.",
            ))

    return findings

def _accessibility_findings(
    url: str,
    audits: Dict[str, Any],
    categories: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Collect lighthouse accessibility audit findings and score

    @Args:
        url (str) -- page url of audit data
        audits (Dict[str, Any]) -- audit data object
        categories (Dict[str, Any]) -- category object
    
    @Returns:
        list of accessibility audit findings (List) 
        overall accessibility audit score
    """
    findings: List[Dict[str, Any]] = []
    audit_ids = _category_audit_ids(categories, "accessibility")

    if not audit_ids:
        audit_ids = ACCESSIBILITY_AUDIT_IDS

    for audit_id in audit_ids:
        audit = audits.get(audit_id, {})
        
        if not isinstance(audit, dict):
            continue
        
        if audit.get("error") == "missing_audit":
            continue
        
        score = audit.get("score")
        manual = audit.get("scoreDisplayMode") == "manual"
        
        if score == 0 or manual:
            severity = _severity_for_accessibility(score if isinstance(score, (int, float)) else None, manual)
            status_note = "Manual review required." if manual else "Automated check failed."
            findings.append(_build_finding(
                category="accessibility",
                title=audit.get("title") or "Accessibility issue",
                description=f"{audit.get('description') or ''} {status_note}".strip(),
                severity=severity,
                score=score if isinstance(score, (int, float)) else None,
                affected_elements=[url],
                standard_reference={
                    "framework": "WCAG",
                    "code": audit_id,
                    "level": None,
                },
                recommendation="Complete the manual review or remediate the accessibility issue and verify in Lighthouse.",
            ))

    return findings


def normalize_lighthouse_results(lighthouse_data: Dict[str, Any]) -> Dict[str, Any]:
    """Noralises lighthouse audit data 
    
    @Args: 
        lighthouse_data (Dict[str, Any]) -- full returned lighthouse audit data
    
    @Returns:
        Normalised dictionary with findings and score for each category
    """
    results = lighthouse_data.get("lighthouse_data", {}) or {}

    findings: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
        "performance": {"mobile": [], "desktop": []},
        "seo": {"mobile": [], "desktop": []},
        "accessibility": {"mobile": [], "desktop": []},
    }
    scores: Dict[str, Dict[str, List[float]]] = {
        "performance": {"mobile": [], "desktop": []},
        "seo": {"mobile": [], "desktop": []},
        "accessibility": {"mobile": [], "desktop": []},
    }

    for url, data in results.items():
        if not isinstance(data, dict) or data.get("status") != "success":
            continue

        for platform in ("mobile", "desktop"):
            platform_obj = data.get(platform, {}) or {}
            audits = platform_obj.get("audits", {}) or {}
            categories = platform_obj.get("categories", {}) or {}

            perf_findings, perf_score = _performance_findings(url, audits, categories)
            findings["performance"][platform].extend(perf_findings)

            if perf_score is not None:
                scores["performance"][platform].append(perf_score)

            findings["seo"][platform].extend(_seo_findings(url, audits))

            cat = categories.get("seo", {})
            score = cat.get("score") if isinstance(cat, dict) else None

            if isinstance(score, (int, float)):
                scores["seo"][platform].append(float(score))

            findings["accessibility"][platform].extend(_accessibility_findings(url, audits, categories))
            access_cat = categories.get("accessibility", {})
            access_score = access_cat.get("score") if isinstance(access_cat, dict) else None

            if isinstance(access_score, (int, float)):
                scores["accessibility"][platform].append(float(access_score))

    summary: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for category in ("performance", "seo", "accessibility"):
        summary[category] = {}

        for platform in ("mobile", "desktop"):
            per_findings = findings[category][platform]
            by_sev = {"critical": 0, "high": 0, "moderate": 0, "advisory": 0}

            for f in per_findings:
                sev = f.get("severity")
                if sev in by_sev:
                    by_sev[sev] += 1

            avg_score = None
            vals = scores[category][platform]

            if vals:
                avg_score = sum(vals) / len(vals)

            summary[category][platform] = {
                "overall_score": avg_score,
                "findings_by_severity": by_sev,
                "risk_summary": _risk_summary(by_sev),
            }

    return {
        "findings": findings,
        "summary": summary,
    }
