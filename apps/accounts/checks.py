from django.conf import settings
from django.core.checks import Warning, register


@register()
def demo_mode_is_loud(app_configs, **kwargs):
    """Passwordless demo login must never be on by accident, so say so on every startup."""
    if not settings.DEMO_MODE:
        return []
    return [
        Warning(
            "DEMO_MODE is ON: anyone can log in without a password as: "
            + (", ".join(settings.DEMO_USERS) or "(nobody: DEMO_USERS is empty)"),
            hint="Use it only on a database with fake data. Remove DEMO_MODE in production.",
            id="accounts.W001",
        )
    ]
