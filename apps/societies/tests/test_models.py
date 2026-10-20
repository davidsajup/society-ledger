import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.societies.models import Flat, Membership, Society
from apps.societies.services import add_member

pytestmark = pytest.mark.django_db


@pytest.fixture
def society_a():
    return Society.objects.create(name="Green Park", slug="green-park")


@pytest.fixture
def society_b():
    return Society.objects.create(name="Lake View", slug="lake-view")


@pytest.fixture
def user():
    return get_user_model().objects.create_user(username="asha", password="x")


# --- Database constraints: these hold even if application code is bypassed -----------------


def test_flat_label_is_unique_within_a_society(society_a):
    Flat.objects.create(society=society_a, label="A-101")
    with pytest.raises(IntegrityError), transaction.atomic():
        Flat.objects.create(society=society_a, label="A-101")


def test_same_flat_label_is_allowed_in_different_societies(society_a, society_b):
    Flat.objects.create(society=society_a, label="A-101")
    Flat.objects.create(society=society_b, label="A-101")  # must not raise


def test_user_has_at_most_one_membership_per_society(society_a, user):
    Membership.objects.create(user=user, society=society_a, role="admin")
    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.create(user=user, society=society_a, role="treasurer")


def test_user_can_belong_to_several_societies_with_different_roles(society_a, society_b, user):
    flat = Flat.objects.create(society=society_a, label="A-101")
    Membership.objects.create(user=user, society=society_a, role="resident", flat=flat)
    Membership.objects.create(user=user, society=society_b, role="treasurer")  # must not raise


def test_database_rejects_resident_without_flat(society_a, user):
    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.create(user=user, society=society_a, role="resident", flat=None)


# --- Service-level rule the database cannot express ----------------------------------------


def test_add_member_rejects_flat_from_another_society(society_a, society_b, user):
    other_flat = Flat.objects.create(society=society_b, label="B-1")
    with pytest.raises(ValidationError):
        add_member(society=society_a, user=user, role="resident", flat=other_flat)
    assert not Membership.objects.exists()


def test_add_member_rejects_flat_for_non_resident(society_a, user):
    flat = Flat.objects.create(society=society_a, label="A-101")
    with pytest.raises(ValidationError):
        add_member(society=society_a, user=user, role="admin", flat=flat)


def test_add_member_creates_resident_with_own_flat(society_a, user):
    flat = Flat.objects.create(society=society_a, label="A-101")
    membership = add_member(society=society_a, user=user, role="resident", flat=flat)
    assert membership.flat == flat


# --- Guard: stops a future tenant-owned model from shipping without scoping ---------------


def test_every_model_with_a_society_fk_has_for_society():
    missing = []
    for model in apps.get_models():
        if model is Society or not model.__module__.startswith("apps."):
            continue
        has_society_fk = any(f.name == "society" for f in model._meta.get_fields())
        if has_society_fk and not hasattr(model.objects, "for_society"):
            missing.append(model.__name__)
    assert not missing, f"Tenant-owned models without for_society(): {missing}"
