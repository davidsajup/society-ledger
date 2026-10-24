from apps.accounts.permissions import IsSettledUser


class IsPlatformAdmin(IsSettledUser):
    """The super admin: a platform operator who sits ABOVE the societies.

    Deliberately not a society role. A super admin has no Membership, so every
    /api/societies/<id>/ route answers 404 for them (tenant isolation is unchanged) and they
    can never read a society's money. Everything under /api/platform/ is onboarding only.
    Checked after IsSettledUser, so a super admin on a temporary password must change it first.
    """

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_superuser
