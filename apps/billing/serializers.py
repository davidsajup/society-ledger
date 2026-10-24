from rest_framework import serializers


class BillingSettingsInputSerializer(serializers.Serializer):
    """What the president sends. Both fields are required: this replaces the whole schedule."""

    billing_cycle_months = serializers.ChoiceField(choices=[1, 3])
    billing_start = serializers.DateField()
    # True only when the president has checked every flat's amount for the new cycle.
    amounts_reviewed = serializers.BooleanField(required=False, default=False)
