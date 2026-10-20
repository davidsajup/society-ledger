from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission

from .models import Membership
from .roles import role_can


class IsSocietyMember(BasePermission):
    """Resolve the tenant from the URL and prove the caller belongs to it.

    The society id comes from the path (`/api/societies/<society_id>/...`), but it is never
    trusted on its own: the caller must have a Membership for exactly that society.
    A non-member gets 404, identical to a society that does not exist, so ids do not leak.
    """

    def has_permission(self, request, view):
        membership = (
            Membership.objects.filter(user=request.user, society_id=view.kwargs["society_id"])
            .select_related("society", "flat")
            .first()
        )
        if membership is None:
            raise NotFound()
        request.membership = membership
        request.society = membership.society
        return True


class HasCapability(BasePermission):
    """Require `view.required_capability` for the caller's role IN THIS society.

    Must come after IsSocietyMember. 403 here is fine: the caller is a member, so they already
    know the society exists.
    """

    def has_permission(self, request, view):
        return role_can(request.membership.role, view.required_capability)
