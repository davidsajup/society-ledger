"""Single source of truth for what each role may do.

Views never ask "is this user a treasurer?". They ask "does this membership have capability X?".
Adding a role later means adding one entry here, with no view changes.
"""

MANAGE_FLATS = "manage_flats"
MANAGE_MEMBERS = "manage_members"
RECORD_PAYMENT = "record_payment"
RECORD_EXPENSE = "record_expense"
VIEW_ALL_BALANCES = "view_all_balances"
VIEW_AUDIT = "view_audit"
VIEW_OWN_DUES = "view_own_dues"

ROLE_PERMISSIONS = {
    "admin": {MANAGE_FLATS, MANAGE_MEMBERS, VIEW_ALL_BALANCES, VIEW_AUDIT, VIEW_OWN_DUES},
    "treasurer": {RECORD_PAYMENT, RECORD_EXPENSE, VIEW_ALL_BALANCES, VIEW_AUDIT, VIEW_OWN_DUES},
    "resident": {VIEW_OWN_DUES},
}


def role_can(role, capability):
    return capability in ROLE_PERMISSIONS.get(role, set())
