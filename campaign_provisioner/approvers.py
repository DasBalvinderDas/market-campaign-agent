"""Parsing of approver email configuration ("Role=a@x.com,b@x.com;Other Role=c@x.com")."""
import re

ALL_ROLES = "*"
_EMAIL = re.compile(r"^[^@\s,;=]+@[^@\s,;=]+\.[^@\s,;=]+$")


def parse(spec: str) -> dict[str, list[str]]:
    """Parse a spec into {role: [emails]}. A bare list of emails applies to every approver role (key "*")."""
    result: dict[str, list[str]] = {}
    for part in [p.strip() for p in (spec or "").split(";") if p.strip()]:
        role, _, emails = part.partition("=") if "=" in part else (ALL_ROLES, "", part)
        role = role.strip() or ALL_ROLES
        for e in [x.strip() for x in emails.split(",") if x.strip()]:
            if not _EMAIL.match(e):
                raise ValueError(f"'{e}' is not a valid email address (in approver setting '{part}')")
            result.setdefault(role, [])
            if e not in result[role]:
                result[role].append(e)
    return result


def expand(config: dict[str, list[str]], roles: list[str]) -> list[dict]:
    """Rows for the approvers table: role-specific emails plus "*" emails for every role."""
    rows = []
    for role in roles:
        emails = list(config.get(role, [])) + [e for e in config.get(ALL_ROLES, []) if e not in config.get(role, [])]
        rows += [{"approver_role": role, "email": e, "active": True} for e in emails]
    return rows
