from rest_framework import serializers

from apps.accounts.credentials import login_status


class CreateSocietySerializer(serializers.Serializer):
    """Input for onboarding a society. Flats and everyone else are added by its president."""

    name = serializers.CharField(max_length=120)
    slug = serializers.SlugField(max_length=50)
    president_name = serializers.CharField(max_length=100)


class ManagerSerializer(serializers.Serializer):
    """A society's president or secretary, as the super admin sees them. No money, no flats."""

    member_id = serializers.IntegerField(source="id")
    name = serializers.CharField(source="user.first_name")
    username = serializers.CharField(source="user.username")
    role = serializers.CharField()
    login_status = serializers.SerializerMethodField()

    def get_login_status(self, obj):
        return login_status(obj.user)
