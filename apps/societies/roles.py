"""Single source of truth for what each role may do.

Views never ask "is this user a treasurer?". They ask "does this membership have capability X?".
Adding a role later means adding one entry here, with no view changes.
"""

VIEW_FLATS = "view_flats"
MANAGE_FLATS = "manage_flats"
MANAGE_MEMBERS = "manage_members"
RECORD_PAYMENT = "record_payment"
REVERSE_ENTRY = "reverse_entry"
RECORD_EXPENSE = "record_expense"
VIEW_EXPENSES = "view_expenses"
VIEW_ALL_BALANCES = "view_all_balances"
VIEW_AUDIT = "view_audit"
VIEW_OWN_DUES = "view_own_dues"

ROLE_PERMISSIONS = {
    "admin": {
        VIEW_FLATS, MANAGE_FLATS, MANAGE_MEMBERS, VIEW_ALL_BALANCES, VIEW_EXPENSES, VIEW_AUDIT,
        VIEW_OWN_DUES,
    },
    "treasurer": {
        VIEW_FLATS, RECORD_PAYMENT, REVERSE_ENTRY, RECORD_EXPENSE, VIEW_EXPENSES, VIEW_ALL_BALANCES,
        VIEW_AUDIT, VIEW_OWN_DUES,
    },
    "resident": {VIEW_OWN_DUES},
}


def role_can(role, capability):
    return capability in ROLE_PERMISSIONS.get(role, set())
