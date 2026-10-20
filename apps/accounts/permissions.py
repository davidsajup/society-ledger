from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated


class PasswordChangeRequired(PermissionDenied):
    default_detail = {
        "detail": "You must change your temporary password before continuing.",
        "code": "password_change_required",
    }


class IsSettledUser(IsAuthenticated):
    """Logged in AND no longer on a temporary password.

    This is the server-side half of "change your password at first login". It is used as the
    default permission and by SocietyScopedView, so a person on a temporary password can reach
    only /auth/me, /auth/logout and /auth/change-password, whatever the browser does.
    """

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.user.must_change_password:
            raise PasswordChangeRequired()
        return True
