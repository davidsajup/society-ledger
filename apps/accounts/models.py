from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Project user model.

    A user's role is NOT stored here; it lives on societies.Membership, because one person can
    belong to several societies with a different role in each.

    The two fields below support admin-issued logins: an admin creates the account with a
    random temporary password, and the person must replace it at first login (enforced on the
    server for every API call) before it expires.
    """

    must_change_password = models.BooleanField(default=False)
    temp_password_expires_at = models.DateTimeField(null=True, blank=True)
