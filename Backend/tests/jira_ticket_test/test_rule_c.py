from app.rules.jira_rules.rule_c import (
    rule_c_01_real_resolutions_only,
    rule_c_02_strip_noise,
    rule_c_03_redact_sensitive,
    rule_c_04_separate_problem_and_solution,
    rule_c_05_chunk_long_text,
)
from ticket_factory import make_ticket, make_comment


def test_c01_rejects_trivial_solution():
    comments = [make_comment("1", "fixed", "2026-09-01T10:00:00+0000")]
    ticket = make_ticket(resolution="Fixed", comments=comments)
    ticket = rule_c_01_real_resolutions_only(ticket)
    assert ticket["rule_results"]["c01_is_real_resolution"] is False


def test_c01_accepts_substantial_solution():
    body = "Reconfigured the warehouse setting on item X and re-ran the batch job."
    comments = [make_comment("1", body, "2026-09-01T10:00:00+0000")]
    ticket = make_ticket(resolution="Fixed", comments=comments)
    ticket = rule_c_01_real_resolutions_only(ticket)
    assert ticket["rule_results"]["c01_is_real_resolution"] is True


def test_c02_strips_signature_lines():
    body = "Real content here.\n--\nSent from my iPhone"
    comments = [make_comment("1", body, "2026-09-01T10:00:00+0000")]
    ticket = make_ticket(comments=comments)
    ticket = rule_c_02_strip_noise(ticket)
    assert "Sent from my iPhone" not in ticket["comments"][0]["body_clean"]
    assert "Real content here." in ticket["comments"][0]["body_clean"]


def test_c03_redacts_email():
    ticket = make_ticket(description="Contact john@client.com for details")
    ticket = rule_c_03_redact_sensitive(ticket)
    assert "john@client.com" not in ticket["description"]
    assert "[EMAIL_REDACTED]" in ticket["description"]
    assert ticket["rule_results"]["c03_sensitive_found"] is True


def test_c03_redacts_credential():
    ticket = make_ticket(description="api_key: sk_live_abc123")
    ticket = rule_c_03_redact_sensitive(ticket)
    assert "sk_live_abc123" not in ticket["description"]
    assert "credential" in ticket["rule_results"]["c03_sensitive_types"]


def test_c04_splits_problem_and_solution():
    body = "The fix was to clear the cached batch queue and restart the service."
    comments = [make_comment("1", body, "2026-09-01T10:00:00+0000")]
    ticket = make_ticket(description="Pick fails on batch item", comments=comments)
    ticket = rule_c_02_strip_noise(ticket)
    ticket = rule_c_03_redact_sensitive(ticket)
    ticket = rule_c_04_separate_problem_and_solution(ticket)
    assert "Pick fails" in ticket["rule_results"]["c04_problem"]
    assert "clear the cached batch" in ticket["rule_results"]["c04_solution"]