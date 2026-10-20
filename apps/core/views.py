from django.db import connection
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])  # explicit opt-out of the deny-by-default setting
def health(request):
    """Liveness + database check. Returns 503 if the database is unreachable."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return Response({"status": "degraded", "db": "error"}, status=503)
    return Response({"status": "ok", "db": "ok"})
