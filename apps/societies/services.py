from django.core.exceptions import ValidationError

from .models import Membership


def add_member(*, society, user, role, flat=None):
    """Give `user` a role in `society`.

    The database cannot check that `flat` belongs to the same society (Django has no composite
    foreign keys), so this function is the only sanctioned way to create a Membership.
    """
    # Errors are keyed by the model field they are about, so an API can show each one next to
    # the right input instead of as a nameless list.
    if flat is not None and flat.society_id != society.id:
        raise ValidationError({"flat": "Flat belongs to a different society."})
    if role != Membership.Role.RESIDENT and flat is not None:
        raise ValidationError({"flat": "Only residents are attached to a flat."})
    if Membership.objects.for_society(society).filter(user=user).exists():
        raise ValidationError({"user": "This person is already a member of this society."})

    membership = Membership(society=society, user=user, role=role, flat=flat)
    membership.full_clean(exclude=["created_at"])  # runs the model-level checks with clear errors
    membership.save()
    return membership
