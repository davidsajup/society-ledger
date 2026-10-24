from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import serializers

from apps.accounts.credentials import login_status

from .models import Flat, Membership
from .services import add_member


class FlatSerializer(serializers.ModelSerializer):
    """`society` is deliberately not a field: the tenant always comes from the URL."""

    class Meta:
        model = Flat
        fields = ["id", "label", "maintenance_amount"]
        # Mirrors the DB check (>= 0). DRF's DecimalField also refuses more than 2 decimals.
        extra_kwargs = {"maintenance_amount": {"min_value": 0}}

    def validate_label(self, value):
        society = self.context["society"]
        clash = Flat.objects.for_society(society).filter(label=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("A flat with this label already exists.")
        return value


def _api_errors(exc):
    """Turn a Django ValidationError into {field: [messages]} using the API's field names."""
    if not hasattr(exc, "error_dict"):
        return {"non_field_errors": exc.messages}
    errors = {}
    for field, messages in exc.message_dict.items():
        name = {"user": "username", "__all__": "non_field_errors"}.get(field, field)
        errors[name] = messages
    return errors


class CreateLoginSerializer(serializers.Serializer):
    """Input for creating a brand-new login. The society comes from the URL, never the body."""

    name = serializers.CharField(max_length=100)
    role = serializers.ChoiceField(choices=Membership.Role.choices)
    flat = serializers.PrimaryKeyRelatedField(
        queryset=Flat.objects.none(), required=False, allow_null=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        society = self.context.get("society")
        if society is not None:
            self.fields["flat"].queryset = Flat.objects.for_society(society)


class ChangeMemberSerializer(serializers.Serializer):
    """Input for changing a member. Absent fields are left alone; `flat: null` clears the flat."""

    role = serializers.ChoiceField(choices=Membership.Role.choices, required=False)
    flat = serializers.PrimaryKeyRelatedField(
        queryset=Flat.objects.none(), required=False, allow_null=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        society = self.context.get("society")
        if society is not None:
            self.fields["flat"].queryset = Flat.objects.for_society(society)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError({"role": ["Choose a role or a flat to change."]})
        return attrs


class MembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True)
    user = serializers.CharField(source="user.username", read_only=True)
    name = serializers.CharField(source="user.first_name", read_only=True)
    login_status = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = [
            "id", "username", "user", "name", "login_status", "role", "flat", "phone", "email",
        ]
        read_only_fields = ["phone", "email"]  # set only by the bulk import

    def get_login_status(self, obj):
        # 'active', 'temporary' (never used) or 'expired'. Lists select_related("user").
        return login_status(obj.user)

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
            raise serializers.ValidationError(_api_errors(exc)) from exc
        except IntegrityError:
            # Two requests added the same person at once: the DB constraint caught the loser.
            raise serializers.ValidationError(
                {"username": ["This person is already a member of this society."]}
            ) from None
