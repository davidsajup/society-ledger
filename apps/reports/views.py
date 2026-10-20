from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import BillingRun
from apps.societies import roles
from apps.societies.views import SocietyScopedView

from .dues import dues_grid
from .selectors import recent_payments, society_summary
from .serializers import (
    BillingRunSerializer,
    DuesSerializer,
    RecentPaymentSerializer,
    SummarySerializer,
)


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


class DuesView(SocietyScopedView, APIView):
    """GET /dues/ (admin, treasurer): flats by month, paid / partial / unpaid. Read-only."""

    required_capabilities = {"GET": roles.VIEW_ALL_BALANCES}

    def get(self, request, society_id):
        return Response(DuesSerializer(dues_grid(request.society)).data)


class BillingRunsView(SocietyScopedView, APIView):
    """GET /billing-runs/ (admin, treasurer): which months were billed, newest first."""

    required_capabilities = {"GET": roles.VIEW_ALL_BALANCES}

    def get(self, request, society_id):
        runs = BillingRun.objects.for_society(request.society).order_by("-period")[:24]
        return Response(BillingRunSerializer(runs, many=True).data)
