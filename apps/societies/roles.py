"""Single source of truth for what each role may do.

Views never ask "is this user a treasurer?". They ask "does this membership have capability X?".
Adding a role later means adding one entry here, with no view changes.
"""

VIEW_FLATS = "view_flats"
MANAGE_FLATS = "manage_flats"
MANAGE_MEMBERS = "manage_members"
VIEW_BILLING_SETTINGS = "view_billing_settings"
MANAGE_BILLING = "manage_billing"
RECORD_PAYMENT = "record_payment"
REVERSE_ENTRY = "reverse_entry"
RECORD_EXPENSE = "record_expense"
VIEW_EXPENSES = "view_expenses"
VIEW_ALL_BALANCES = "view_all_balances"
VIEW_AUDIT = "view_audit"
VIEW_OWN_DUES = "view_own_dues"
SUBMIT_CLAIM = "submit_claim"
RESOLVE_CLAIM = "resolve_claim"

# What every office-bearer can do. Payments are deliberately included for all three, so that
# when one of them pays their own dues another can record it (nobody may record or reverse a
# payment for the flat they live in; see ledger.services.SelfPaymentNotAllowed).
_OFFICE_BEARER = {
    VIEW_FLATS,
    VIEW_ALL_BALANCES,
    VIEW_EXPENSES,
    VIEW_AUDIT,
    VIEW_BILLING_SETTINGS,
    VIEW_OWN_DUES,
    SUBMIT_CLAIM,
    RESOLVE_CLAIM,
    RECORD_PAYMENT,
    REVERSE_ENTRY,
}

ROLE_PERMISSIONS = {
    # Only the president decides how often the society is billed and when billing starts.
    "president": _OFFICE_BEARER | {MANAGE_FLATS, MANAGE_MEMBERS, MANAGE_BILLING},
    "secretary": _OFFICE_BEARER | {MANAGE_FLATS, MANAGE_MEMBERS},
    # Only the treasurer records spending (money out).
    "treasurer": _OFFICE_BEARER | {RECORD_EXPENSE},
    "resident": {VIEW_OWN_DUES, SUBMIT_CLAIM},
}


def roles_with(capability):
    """Every role that has `capability` (used for rules like 'keep at least one manager')."""
    return sorted(role for role, caps in ROLE_PERMISSIONS.items() if capability in caps)


def role_can(role, capability):
    return capability in ROLE_PERMISSIONS.get(role, set())
