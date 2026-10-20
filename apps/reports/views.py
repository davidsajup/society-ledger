from rest_framework.response import Response
from rest_framework.views import APIView

from apps.societies import roles
from apps.societies.views import SocietyScopedView

from .selectors import recent_payments, society_summary
from .serializers import RecentPaymentSerializer, SummarySerializer


class SummaryView(SocietyScopedView, APIView):
    """GET /summary/ (admin, treasurer): billed / collected / outstanding / spent, per flat too."""

    required_capabilities = {"GET": roles.VIEW_ALL_BALANCES}

    def get(self, request, society_id):
        return Response(SummarySerializer(society_summary(request.society)).data)


class ActivityView(SocietyScopedView, APIView):
    """GET /activity/ (admin, treasurer): the newest payments across the society."""

    required_capabilities = {"GET": roles.VIEW_ALL_BALANCES}

    def get(self, request, society_id):
        rows = recent_payments(request.society)
        return Response(RecentPaymentSerializer(rows, many=True).data)
