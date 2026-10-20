from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission

from apps.societies.roles import VIEW_ALL_BALANCES, role_can


class OwnFlatOrAllBalances(BasePermission):
    """Object-level permission for a flat's ledger.

    Admins and treasurers (VIEW_ALL_BALANCES) may read any flat in their society. A resident
    may read only the flat on their own Membership. Anything else is a 404, not a 403: a
    resident must not be able to tell which other flats exist.

    DRF only calls this when the view calls self.check_object_permissions(request, flat).
    """

    def has_permission(self, request, view):
        return True  # the capability check already ran; this class only guards the object

    def has_object_permission(self, request, view, flat):
        membership = request.membership
        if role_can(membership.role, VIEW_ALL_BALANCES) or membership.flat_id == flat.id:
            return True
        raise NotFound()
