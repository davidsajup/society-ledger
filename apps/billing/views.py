from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.societies import roles
from apps.societies.models import Flat, Society
from apps.societies.serializers import _api_errors
from apps.societies.views import SocietyScopedView

from . import services
from .serializers import BillingSettingsInputSerializer


def settings_payload(society):
    """How the society is billed, and whether that can still be changed."""
    return {
        "billing_cycle_months": society.billing_cycle_months,
        "billing_start": society.billing_start,
        "locked": services.billing_has_started(society),
        "flats_with_amounts": Flat.objects.for_society(society)
        .filter(maintenance_amount__gt=0)
        .count(),
    }


class BillingSettingsView(SocietyScopedView, APIView):
    """GET /billing-settings/ (every office-bearer), PUT (president only, until billing starts)."""

    required_capabilities = {
        "GET": roles.VIEW_BILLING_SETTINGS,
        "PUT": roles.MANAGE_BILLING,
    }

    def get(self, request, society_id):
        return Response(self._body(request.society))

    def put(self, request, society_id):
        data = BillingSettingsInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            society, _changed = services.change_billing_settings(
                society=request.society,
                actor=request.user,
                cycle_months=data.validated_data["billing_cycle_months"],
                start=data.validated_data["billing_start"],
                amounts_reviewed=data.validated_data["amounts_reviewed"],
            )
        except services.BillingAlreadyStarted as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(_api_errors(exc)) from exc
        return Response(self._body(society))

    def _body(self, society):
        # Re-read: request.society was loaded before any change made by this request.
        return settings_payload(Society.objects.get(pk=society.pk))
