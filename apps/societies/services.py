from django.core.exceptions import ValidationError

from .models import Membership


def add_member(*, society, user, role, flat=None):
    """Give `user` a role in `society`.

    The database cannot check that `flat` belongs to the same society (Django has no composite
    foreign keys), so this function is the only sanctioned way to create a Membership.
    """
    if flat is not None and flat.society_id != society.id:
        raise ValidationError("Flat belongs to a different society.")
    if role != Membership.Role.RESIDENT and flat is not None:
        raise ValidationError("Only residents are attached to a flat.")

    membership = Membership(society=society, user=user, role=role, flat=flat)
    membership.full_clean(exclude=["created_at"])  # runs the model-level checks with clear errors
    membership.save()
    return membership
