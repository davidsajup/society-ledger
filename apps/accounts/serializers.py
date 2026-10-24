from rest_framework import serializers

from apps.societies.models import Membership


class DemoLoginSerializer(serializers.Serializer):
    username = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False, max_length=128)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


def serialize_me(user):
    """The caller's own identity and memberships.

    This is a user-scoped query (not a society-scoped one) on purpose: it only ever returns
    rows belonging to request.user.
    """
    memberships = Membership.objects.filter(user=user).select_related("society", "flat")
    return {
        "id": user.id,
        "username": user.username,
        "must_change_password": user.must_change_password,
        # The super admin onboards societies; they belong to none and see no money.
        "is_platform_admin": user.is_superuser,
        "memberships": [
            {
                "society_id": m.society_id,
                "society_name": m.society.name,
                "role": m.role,
                "flat_id": m.flat_id,
                "flat_label": m.flat.label if m.flat else None,
            }
            for m in memberships
        ],
    }
