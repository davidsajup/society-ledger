from rest_framework.response import Response
from rest_framework.views import APIView

from apps.societies import roles
from apps.societies.views import SocietyScopedView

from .models import AuditLog
from .serializers import AuditLogSerializer

LIST_PAGE = 200  # newest rows returned; real pagination can come when there are more


class AuditLogListView(SocietyScopedView, APIView):
    """GET /audit/  (office-bearers). Read-only: there is no way to write through HTTP."""

    required_capabilities = {"GET": roles.VIEW_AUDIT}

    def get(self, request, society_id):
        rows = (
            AuditLog.objects.for_society(request.society)
            .select_related("actor")  # avoids one query per row (N+1)
            .order_by("-created_at", "-id")[:LIST_PAGE]
        )
        return Response(AuditLogSerializer(rows, many=True).data)
