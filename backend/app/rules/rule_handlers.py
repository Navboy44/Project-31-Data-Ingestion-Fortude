import re
from calendar import monthrange
from datetime import datetime, timezone


SENSITIVE_PATTERNS = {
    "password": r"\bpassword\s*[:=]\s*\S+",
    "api_key": r"\bapi[ _]key\s*[:=]\s*\S+",
    "secret": r"\bsecret\s*[:=]\s*\S+",
    "token": r"\btoken\s*[:=]\s*\S+",
}

CATEGORY_KEYWORDS = [
    ("how-to", ("how to", "setup", "configure", "configuration", "guide")),
    ("troubleshooting", ("error", "issue", "fix", "problem", "troubleshoot")),
    ("policy", ("policy", "procedure", "standard")),
    ("compliance", ("compliance", "audit", "regulation")),
]


def _apply_knowledge_base_rules(document):
    """Classify a KB document and decide whether it is active, archived, or rejected."""
    text = f"{document.get('title') or ''}\n{document.get('content') or ''}"
    lowered_text = text.casefold()

    # Store only the type of secret found, never the matched secret value.
    sensitive_matches = [
        name
        for name, pattern in SENSITIVE_PATTERNS.items()
        if re.search(pattern, text, re.IGNORECASE)
    ]
    document["contains_sensitive_content"] = bool(sensitive_matches)
    document["sensitive_matches"] = sensitive_matches

    category = "general"
    # The first matching keyword group gives the document one stable category.
    for name, keywords in CATEGORY_KEYWORDS:
        if any(keyword in lowered_text for keyword in keywords):
            category = name
            break
    document["kb_category"] = category
    tags = document.setdefault("tags", [])
    if category not in tags:
        tags.append(category)

    modified_at = document.get("modified_at")
    view_count = document.get("view_count")
    is_old = False
    if modified_at:
        try:
            modified = datetime.fromisoformat(modified_at.replace("Z", "+00:00"))
            if modified.tzinfo is None:
                modified = modified.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            # Use calendar months so the stale threshold stays exactly 18 months.
            cutoff_month = now.month - 18
            cutoff_year = now.year
            while cutoff_month <= 0:
                cutoff_month += 12
                cutoff_year -= 1
            cutoff_day = min(now.day, monthrange(cutoff_year, cutoff_month)[1])
            cutoff = now.replace(
                year=cutoff_year, month=cutoff_month, day=cutoff_day
            )
            is_old = modified <= cutoff
        except (TypeError, ValueError):
            pass

    # A document is stale only when it is both old and rarely viewed.
    document["is_stale"] = is_old and view_count is not None and view_count < 10
    if sensitive_matches:
        # Sensitive rejection takes priority, even if the document is also stale.
        document["kb_status"] = "rejected_sensitive"
    elif document["is_stale"]:
        document["kb_status"] = "archive"
    else:
        document["kb_status"] = "active"


def apply_selected_rules(document, rule_name):
    """Apply the selected business-rule set and record which rule was used."""
    if rule_name == "Infor Sales Rules":
        document.setdefault("tags", []).append("sales")
        document["metadata"] = {
            "category": "sales",
            "source": "sales-rule",
        }
    elif rule_name == "L3 Ticket Rules":
        document.setdefault("tags", []).append("support")
        document["metadata"] = {
            "priority": "high",
            "source": "support-rule",
        }
    elif rule_name == "Knowledge Base Rules":
        document.setdefault("tags", []).append("knowledge")
        _apply_knowledge_base_rules(document)
        document["metadata"] = {
            "summary": "knowledge-base-entry",
            "source": "knowledge-rule",
        }
    else:
        document["metadata"] = {"source": "default-rule"}

    document["rule_applied"] = rule_name
    return document
