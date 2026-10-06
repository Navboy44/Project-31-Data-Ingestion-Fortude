from datetime import datetime, timezone
import ZoneInfo
CRITICAL_KEYWORDS = ["outage", "data loss", "production down", "breach"]

#because tickets with enterprise in them only have 4 SLA, if not 24 hrs SLA
def get_sla_hours(customer_tier):
    if str(customer_tier).lower() == "enterprise":
        return 4
    return 24

#checks critical words
def has_critical_keyword(ticket):
    title = ticket.get("title") or ""
    description = ticket.get("description") or ""
    text = (title + " " + description).lower()

    found_keyword = False
    for keyword in CRITICAL_KEYWORDS:
        if keyword in text:
            found_keyword = True

    return found_keyword


def get_hours_since_created(created_at):
    if not created_at:
        return 0

    try:
        created_time = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S.%f%z")
        current_time = datetime.now(ZoneInfo("Australia/Melbourne"))
        hours = (current_time - created_time).total_seconds() / 3600
        return round(hours, 2)
    except Exception:
        return 0

#transform ticket according to breach risk, escalation level etc.
def transform_canonical_ticket_for_l3(ticket):
    critical_keyword_found = has_critical_keyword(ticket)
    sla_hours = get_sla_hours(ticket.get("customer_tier"))
    hours_since_created = get_hours_since_created(ticket.get("created_at"))
    if not ticket.get("is_L3"):
        return None
    breach_risk_score = 0
    if sla_hours > 0:
        breach_risk_score = round(min(hours_since_created / sla_hours, 1), 2)

    escalation_level = "NORMAL"
    page_on_call = False

    if breach_risk_score >= 0.75:
        escalation_level = "HIGH"
        page_on_call = True

    if critical_keyword_found:
        escalation_level = "IMMEDIATE"
        page_on_call = True

    transformed_ticket = {
        **ticket,
        "sla_hours": sla_hours,
        "hours_since_created": hours_since_created,
        "breach_risk_score": breach_risk_score,
        "critical_keyword_detected": critical_keyword_found,
        "escalation_level": escalation_level,
        "page_on_call": page_on_call,
        "duplicate_check_key": ticket.get("source") + ":" + ticket.get("ticket_key"),
    }

    return transformed_ticket


def transform_canonical_tickets_for_l3(tickets):
    transformed_tickets = []

    for ticket in tickets:
        transformed_ticket = transform_canonical_ticket_for_l3(ticket)
        if transformed_ticket!= None:
            transformed_tickets.append(transformed_ticket)

    return transformed_tickets