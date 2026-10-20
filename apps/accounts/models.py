from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Project user model.

    Deliberately empty: it exists so AUTH_USER_MODEL can be changed later without a painful
    migration. A user's role is NOT stored here; it lives on societies.Membership, because one
    person can belong to several societies with a different role in each.
    """
