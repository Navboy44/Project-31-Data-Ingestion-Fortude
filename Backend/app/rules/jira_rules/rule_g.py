"""
Rule set G: Change and release audit evidence.

Answers the compliance question: can we prove that every change made to
a client's production system was authorised before it shipped?

Rules
-----
G-01  Check that change evidence is complete
G-02  Check that the approval is real, not just a ticket status
G-03  Check that approval precedes deployment
G-04  Check separation of duties
G-05  Handle emergency changes through retro-approval
G-06  Catch mislabelled routine changes on sensitive systems
G-07  Find orphan deployments with no change ticket
G-08  Hash the evidence record so later tampering is detectable

Notes
-----
G rules record findings. They never block a change or reject a ticket.
They produce the evidence pack continuously so an audit request becomes
a report rather than a project.
"""

import hashlib
import json
from datetime import datetime


def _parse_ts(value):
    """
    Parse a Jira-style ISO 8601 timestamp into a datetime.

    Returns None if the value is missing or unparseable.
    """
    if not value:
        return None

    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# G-01 Check completeness
# ---------------------------------------------------------------------------

def rule_g_01_check_completeness(ticket):
    """
    Check that all required change evidence is recorded.

    Required evidence:
        risk_level, rollback_plan, testing_evidence, description

    Writes to rule_results:
        g01_missing    (list[str])
        g01_complete   (bool)
    """
    missing_evidence = []

    if not ticket.get("risk_level"):
        missing_evidence.append("risk_level")
    if not ticket.get("rollback_plan"):
        missing_evidence.append("rollback_plan")
    if not ticket.get("testing_evidence"):
        missing_evidence.append("testing_evidence")
    if not ticket.get("description"):
        missing_evidence.append("reason_for_change")

    ticket["rule_results"]["g01_missing"] = missing_evidence
    ticket["rule_results"]["g01_complete"] = len(missing_evidence) == 0
    return ticket


# ---------------------------------------------------------------------------
# G-02 Check the approval is real
# ---------------------------------------------------------------------------
# Confirms somebody on the approver list actually approved, not just that
# the ticket reached an approved status. This is a common audit finding:
# a ticket status says "Approved" but no approver on record approved it.
# ---------------------------------------------------------------------------

def rule_g_02_check_real_approval(ticket):
    """
    Confirm at least one approver on the list actually approved.

    Writes to rule_results:
        g02_real_approval  (bool)
        g02_approved_by    (list[str])
    """
    approvers = [approver.lower() for approver in (ticket.get("approver_list") or [])]
    approvals = ticket.get("approvals", [])

    approved_by = [
        (approval.get("approver") or "").lower()
        for approval in approvals
        if (approval.get("status") or "").lower() == "approved"
    ]

    has_real_approval = any(approver in approvers for approver in approved_by)

    ticket["rule_results"]["g02_real_approval"] = has_real_approval
    ticket["rule_results"]["g02_approved_by"] = approved_by
    return ticket


# ---------------------------------------------------------------------------
# G-03 Check the order of events
# ---------------------------------------------------------------------------
# Approval timestamp must precede deployment timestamp. This is one of
# the most common real audit failures.
# ---------------------------------------------------------------------------

def rule_g_03_check_order_of_events(ticket):
    """
    Confirm the earliest approval timestamp precedes the deployment.

    Uses the earliest approval on record. If either timestamp is missing,
    the check fails, because absence of evidence is itself a finding.

    Writes to rule_results:
        g03_approval_before_deployment  (bool)
    """
    approvals = ticket.get("approvals", [])
    deployment_timestamp = _parse_ts(ticket.get("deployment_timestamp"))

    earliest_approval_timestamp = None
    for approval in approvals:
        approval_timestamp = _parse_ts(approval.get("created"))
        if approval_timestamp and (
            earliest_approval_timestamp is None
            or approval_timestamp < earliest_approval_timestamp
        ):
            earliest_approval_timestamp = approval_timestamp

    if earliest_approval_timestamp and deployment_timestamp:
        is_valid_order = earliest_approval_timestamp < deployment_timestamp
    else:
        is_valid_order = False

    ticket["rule_results"]["g03_approval_before_deployment"] = is_valid_order
    return ticket


# ---------------------------------------------------------------------------
# G-04 Check separation of duties
# ---------------------------------------------------------------------------
# The requester must not also be an approver and must not also be the
# deployer. This is a standard controls requirement in regulated sectors.
# ---------------------------------------------------------------------------

def rule_g_04_check_separation_of_duties(ticket):
    """
    Confirm the requester, approver, and deployer are distinct people.

    Writes to rule_results:
        g04_separation_ok  (bool)
    """
    requester = (ticket.get("reporter") or "").lower()
    approvers = [approver.lower() for approver in (ticket.get("approver_list") or [])]
    deployer = (ticket.get("assignee") or "").lower()

    requester_is_approver = requester in approvers
    requester_is_deployer = requester == deployer

    ticket["rule_results"]["g04_separation_ok"] = not (
        requester_is_approver or requester_is_deployer
    )
    return ticket


# ---------------------------------------------------------------------------
# G-05 Handle emergency changes properly
# ---------------------------------------------------------------------------
# Emergency changes may skip advance approval but must be approved
# retrospectively within a configured window. They are tracked separately,
# not exempted.
# ---------------------------------------------------------------------------

def rule_g_05_handle_emergency_change(ticket):
    """
    Flag emergency changes and mark them for retro-approval.

    Writes to rule_results:
        g05_is_emergency              (bool)
        g05_requires_retro_approval   (bool)
    """
    is_emergency = bool(ticket.get("emergency_change"))

    ticket["rule_results"]["g05_is_emergency"] = is_emergency
    ticket["rule_results"]["g05_requires_retro_approval"] = is_emergency
    return ticket


# ---------------------------------------------------------------------------
# G-06 Catch mislabelled changes
# ---------------------------------------------------------------------------
# A change marked routine that touches a system on the sensitive list is
# escalated for review. This is one of the three mundane failures
# auditors actually find.
# ---------------------------------------------------------------------------

def rule_g_06_catch_mislabelled_change(ticket):
    """
    Flag changes marked routine that touch a sensitive system.

    Writes to rule_results:
        g06_mislabelled  (bool)
    """
    change_type = (ticket.get("change_type") or "").lower()
    touches_sensitive_system = bool(ticket.get("sensitive_system"))

    ticket["rule_results"]["g06_mislabelled"] = (
        change_type == "routine" and touches_sensitive_system
    )
    return ticket


# ---------------------------------------------------------------------------
# G-07 Find orphan deployments
# ---------------------------------------------------------------------------
# A deployment with no matching change ticket is flagged as unauthorised.
# This rule works on the ticket itself; the cross-ticket orphan check is
# performed by a writer that has visibility over all deployments.
# ---------------------------------------------------------------------------

def rule_g_07_find_orphan_deployments(ticket):
    """
    Flag deployments that are not backed by a change ticket.

    Writes to rule_results:
        g07_orphan  (bool)
    """
    has_deployment = bool(ticket.get("deployment_timestamp"))
    has_change_ticket = bool(ticket.get("ticket_key"))

    ticket["rule_results"]["g07_orphan"] = has_deployment and not has_change_ticket
    return ticket


# ---------------------------------------------------------------------------
# G-08 Protect the evidence
# ---------------------------------------------------------------------------
# Hashes the evidence record so later tampering is detectable. A later
# audit can recompute the hash and compare.
# ---------------------------------------------------------------------------

def rule_g_08_protect_evidence(ticket):
    """
    Store a SHA-256 hash of the evidence record.

    The hash covers the ticket key, approvals, deployment timestamp,
    attachments, risk level, and emergency flag. Any later change to
    those fields changes the hash, which is detectable.

    Writes to rule_results:
        g08_evidence_hash  (str)
    """
    evidence = {
        "ticket_key": ticket.get("ticket_key"),
        "approvals": ticket.get("approvals", []),
        "deployment_timestamp": ticket.get("deployment_timestamp"),
        "attachments": ticket.get("attachments", []),
        "risk_level": ticket.get("risk_level"),
        "emergency_change": ticket.get("emergency_change"),
    }

    payload = json.dumps(evidence, sort_keys=True, default=str).encode("utf-8")
    ticket["rule_results"]["g08_evidence_hash"] = hashlib.sha256(payload).hexdigest()
    return ticket


RULES = [
    rule_g_01_check_completeness,
    rule_g_02_check_real_approval,
    rule_g_03_check_order_of_events,
    rule_g_04_check_separation_of_duties,
    rule_g_05_handle_emergency_change,
    rule_g_06_catch_mislabelled_change,
    rule_g_07_find_orphan_deployments,
    rule_g_08_protect_evidence,
]