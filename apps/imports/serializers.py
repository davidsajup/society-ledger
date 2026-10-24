from rest_framework import serializers

from .parsing import MAX_ROWS


class ImportRowSerializer(serializers.Serializer):
    """One row as the browser sends it back to confirm. All text: clean_rows() decides if it is
    valid, so this only bounds the size of what we accept."""

    row = serializers.IntegerField(min_value=0, max_value=1_000_000, required=False, default=0)
    flat = serializers.CharField(max_length=200, allow_blank=True, required=False, default="")
    name = serializers.CharField(max_length=300, allow_blank=True, required=False, default="")
    phone = serializers.CharField(max_length=100, allow_blank=True, required=False, default="")
    email = serializers.CharField(max_length=300, allow_blank=True, required=False, default="")
    maintenance = serializers.CharField(
        max_length=100, allow_blank=True, required=False, default=""
    )
    role = serializers.CharField(max_length=50, allow_blank=True, required=False, default="")


class ConfirmImportSerializer(serializers.Serializer):
    rows = ImportRowSerializer(many=True, allow_empty=False, max_length=MAX_ROWS)
