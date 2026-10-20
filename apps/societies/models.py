from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.tenancy import TenantQuerySet


class Society(models.Model):
    """The tenant. Every tenant-owned row points back to one Society."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "societies"

    def __str__(self):
        return self.name


class Flat(models.Model):
    society = models.ForeignKey(Society, on_delete=models.PROTECT, related_name="flats")
    label = models.CharField(max_length=20)  # e.g. "A-101"
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantQuerySet.as_manager()

    class Meta:
        constraints = [
            # Two societies may both have "A-101"; one society may not have it twice.
            models.UniqueConstraint(
                fields=["society", "label"], name="flat_label_unique_per_society"
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.society_id})"


class Membership(models.Model):
    """Links a user to a society with one role. Roles are per society, not global."""

    class Role(models.TextChoices):
        ADMIN = "admin"
        TREASURER = "treasurer"
        RESIDENT = "resident"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    society = models.ForeignKey(Society, on_delete=models.PROTECT, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices)
    flat = models.ForeignKey(
        Flat, null=True, blank=True, on_delete=models.PROTECT, related_name="memberships"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "society"], name="one_membership_per_user_per_society"
            ),
            # `choices` is only checked by Django; this makes Postgres refuse unknown roles too.
            models.CheckConstraint(
                condition=Q(role__in=["admin", "treasurer", "resident"]),
                name="membership_role_valid",
            ),
            # A resident must be attached to a flat; the database refuses it otherwise.
            models.CheckConstraint(
                condition=~Q(role="resident") | Q(flat__isnull=False),
                name="resident_requires_flat",
            ),
        ]

    def __str__(self):
        return f"{self.user_id} is {self.role} in {self.society_id}"
