from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Flat, Membership
from .services import add_member


class FlatSerializer(serializers.ModelSerializer):
    """`society` is deliberately not a field: the tenant always comes from the URL."""

    class Meta:
        model = Flat
        fields = ["id", "label", "monthly_maintenance"]
        # Mirrors the DB check (>= 0). DRF's DecimalField also refuses more than 2 decimals.
        extra_kwargs = {"monthly_maintenance": {"min_value": 0}}

    def validate_label(self, value):
        society = self.context["society"]
        clash = Flat.objects.for_society(society).filter(label=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("A flat with this label already exists.")
        return value


class MembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True)
    user = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "username", "user", "role", "flat"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        society = self.context.get("society")
        if society is not None:
            # A flat id from another society is "invalid pk", same as one that does not exist.
            self.fields["flat"].queryset = Flat.objects.for_society(society)

    def create(self, validated_data):
        try:
            user = get_user_model().objects.get(username=validated_data["username"])
        except get_user_model().DoesNotExist:
            raise serializers.ValidationError({"username": "No such user."}) from None
        try:
            return add_member(
                society=self.context["society"],
                user=user,
                role=validated_data["role"],
                flat=validated_data.get("flat"),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
