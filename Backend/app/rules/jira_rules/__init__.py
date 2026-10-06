from app.rules.jira_rules import rule_a
from app.rules.jira_rules import rule_b
from app.rules.jira_rules import rule_c
from app.rules.jira_rules import rule_d
from app.rules.jira_rules import rule_f
from app.rules.jira_rules import rule_g

DEFAULT_RULE_SET = "ALL"
#list to call all rules
ALL_RULE_ORDER = ["A", "B", "C", "D", "F", "G"]

#dict to name all rulesets, ensure the name above is the same as the key below
RULE_SETS = {
    "A": rule_a.RULES,
    "B": rule_b.RULES,
    "C": rule_c.RULES,
    "D": rule_d.RULES,
    "F": rule_f.RULES,
    "G": rule_g.RULES,
    "L3": rule_a.RULES,
}

