from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id", "action", "actor", "flat", "object_type", "object_id", "amount", "data",
            "created_at",
        ]
        read_only_fields = fields

    def get_actor(self, obj):
        # Null actor = a system job (e.g. the billing task).
        return obj.actor.username if obj.actor else "system"
