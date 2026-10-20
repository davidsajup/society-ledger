from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.credentials import make_username, set_temporary_password
from apps.audit import services as audit
from apps.audit.models import AuditLog

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


class CredentialsNotAllowed(Exception):
    """The admin may not (re)issue a login for this person; the message says why."""


@transaction.atomic
def create_member_login(*, society, actor, name, role, flat=None):
    """Create a NEW user with a random temporary password and make them a member.

    Returns (membership, temporary_password). The password exists in plain text only here and
    in the one response that hands it to the admin; it is stored hashed and never audited.
    The account and the membership are created together, so there is no half-made user.
    """
    name = name.strip()
    if not name:
        raise ValidationError({"name": "Enter the person's name."})
    if flat is not None and flat.society_id != society.id:
        raise ValidationError({"flat": "Flat belongs to a different society."})
    if role == Membership.Role.RESIDENT and flat is None:
        raise ValidationError({"flat": "A resident needs a flat."})
    if role != Membership.Role.RESIDENT and flat is not None:
        raise ValidationError({"flat": "Only residents are attached to a flat."})

    user = get_user_model()(
        username=make_username(society, name, flat.label if flat else None, role),
        first_name=name[:150],
    )
    temporary_password = set_temporary_password(user)
    user.save()
    membership = Membership.objects.create(society=society, user=user, role=role, flat=flat)
    audit.record(
        society=society,
        actor=actor,
        action=AuditLog.Action.MEMBER_CREATED,
        flat=flat,
        object_type="membership",
        object_id=membership.pk,
        data={"username": user.username, "role": role},
    )
    return membership, temporary_password


@transaction.atomic
def reissue_credentials(*, society, actor, membership):
    """Give an existing member a new random temporary password (and end their sessions).

    Refused when it would let one society's admin touch an account outside their society:
    staff/superusers, people who also belong to another society, and the admin themselves.
    """
    user = membership.user
    if user.is_staff or user.is_superuser:
        raise CredentialsNotAllowed("This account cannot be managed here.")
    if user.pk == actor.pk:
        raise CredentialsNotAllowed("Use Change password to change your own password.")
    if Membership.objects.filter(user=user).exclude(society=society).exists():
        raise CredentialsNotAllowed(
            "This person also belongs to another society, so only they can change their password."
        )

    temporary_password = set_temporary_password(user)
    user.save(update_fields=["password", "must_change_password", "temp_password_expires_at"])
    audit.record(
        society=society,
        actor=actor,
        action=AuditLog.Action.CREDENTIALS_REISSUED,
        flat=membership.flat,
        object_type="membership",
        object_id=membership.pk,
        data={"username": user.username},
    )
    return temporary_password
