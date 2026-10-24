from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.societies import roles
from apps.societies.models import Flat
from apps.societies.views import SocietyScopedView

from . import services
from .models import LedgerEntry
from .permissions import OwnFlatOrAllBalances
from .selectors import outstanding_for_flat
from .serializers import (
    FlatLedgerSerializer,
    LedgerEntrySerializer,
    PaymentInputSerializer,
    ReversalInputSerializer,
)

LEDGER_PAGE = 200  # newest entries returned; real pagination can come when a flat has more


def get_or_404(queryset, pk):
    """Every "not found" in this module raises the SAME NotFound, so the response body never
    reveals whether an id is missing, in another society, or hidden by an object permission."""
    obj = queryset.filter(pk=pk).first()
    if obj is None:
        raise NotFound()
    return obj


def get_flat(request, flat_id):
    # Scoped by society: another society's flat id is simply "not found".
    return get_or_404(Flat.objects.for_society(request.society), flat_id)


class PaymentCreateView(SocietyScopedView, APIView):
    """POST /flats/<flat_id>/payments/  (treasurer). Optional header: Idempotency-Key."""

    required_capabilities = {"POST": roles.RECORD_PAYMENT}

    def post(self, request, society_id, flat_id):
        flat = get_flat(request, flat_id)
        data = PaymentInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)

        key = request.headers.get("Idempotency-Key")
        if key is not None and not (1 <= len(key) <= 64 and key.isprintable()):
            raise ValidationError({"Idempotency-Key": "Must be 1-64 printable characters."})

        try:
            entry, created = services.record_payment(
                society=request.society,
                flat=flat,
                amount=data.validated_data["amount"],
                actor=request.user,
                idempotency_key=key,
                note=data.validated_data["note"],
                confirm_duplicate=data.validated_data["confirm_duplicate"],
            )
        except services.PaymentExceedsOutstanding as exc:
            raise ValidationError(
                {"amount": f"Exceeds the amount owed ({exc.outstanding})."}
            ) from exc
        except services.SelfPaymentNotAllowed as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except services.IdempotencyKeyReused:
            return Response(
                {
                    "code": "idempotency_key_reused",
                    "detail": "Idempotency-Key was already used for a different request.",
                },
                status=status.HTTP_409_CONFLICT,
            )
        except services.PossibleDuplicatePayment as exc:
            # Nothing was written. Resend with confirm_duplicate=true to record it anyway.
            return Response(
                {
                    "code": "possible_duplicate",
                    "detail": str(exc),
                    "previous": {
                        "amount": str(exc.previous.amount),
                        "created_at": exc.previous.created_at.isoformat(),
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )

        # 201 for a new payment, 200 when a retry gets the original back.
        return Response(
            LedgerEntrySerializer(entry).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class FlatLedgerView(SocietyScopedView, APIView):
    """GET /flats/<flat_id>/ledger/  What a flat owes plus its newest entries."""

    permission_classes = [*SocietyScopedView.permission_classes, OwnFlatOrAllBalances]
    required_capabilities = {"GET": roles.VIEW_OWN_DUES}

    def get(self, request, society_id, flat_id):
        flat = get_flat(request, flat_id)
        self.check_object_permissions(request, flat)  # a resident may only see their own flat

        entries = (
            LedgerEntry.objects.for_society(request.society)
            .filter(flat=flat)
            .select_related("created_by")  # recorded_by, without one query per row
            .order_by("-created_at", "-id")[:LEDGER_PAGE]
        )
        return Response(
            FlatLedgerSerializer(
                {"flat": flat, "outstanding": outstanding_for_flat(flat), "entries": entries}
            ).data
        )


class EntryReverseView(SocietyScopedView, APIView):
    """POST /entries/<entry_id>/reverse/  (treasurer)."""

    required_capabilities = {"POST": roles.REVERSE_ENTRY}

    def post(self, request, society_id, entry_id):
        entry = get_or_404(LedgerEntry.objects.for_society(request.society), entry_id)
        data = ReversalInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)

        try:
            reversal = services.reverse_entry(
                society=request.society,
                entry=entry,
                actor=request.user,
                note=data.validated_data["note"],
            )
        except services.SelfPaymentNotAllowed as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except services.ReversalNotAllowed as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(LedgerEntrySerializer(reversal).data, status=status.HTTP_201_CREATED)
