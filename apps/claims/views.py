from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.ledger import services as ledger
from apps.ledger.permissions import OwnFlatOrAllBalances
from apps.ledger.views import get_flat, get_or_404
from apps.societies import roles
from apps.societies.serializers import _api_errors
from apps.societies.views import SocietyScopedView

from . import services
from .models import PaymentClaim
from .serializers import (
    AcceptInputSerializer,
    ClaimInputSerializer,
    ClaimSerializer,
    RejectInputSerializer,
)

PAGE = 200  # newest claims returned; real pagination can come when there are more


def claims_for(society):
    return PaymentClaim.objects.for_society(society).select_related("flat", "claimed_by")


def conflict(code, detail, **extra):
    return Response({"code": code, "detail": detail, **extra}, status=status.HTTP_409_CONFLICT)


def not_pending(exc):
    return conflict("claim_not_pending", str(exc), claim_status=exc.status)


class FlatClaimsView(SocietyScopedView, APIView):
    """GET/POST /flats/<flat_id>/payment-claims/

    GET: a flat's claims (a resident only for their own flat; office-bearers for any).
    POST: "I have paid", only for the flat you live in. Optional header: Idempotency-Key.
    """

    permission_classes = [*SocietyScopedView.permission_classes, OwnFlatOrAllBalances]
    required_capabilities = {"GET": roles.VIEW_OWN_DUES, "POST": roles.SUBMIT_CLAIM}
    throttle_scope = "claim"

    def get_throttles(self):
        # Only submitting is rate-limited; reading your own claims is not.
        return [ScopedRateThrottle()] if self.request.method == "POST" else []

    def get(self, request, society_id, flat_id):
        flat = get_flat(request, flat_id)
        self.check_object_permissions(request, flat)
        claims = claims_for(request.society).filter(flat=flat).order_by("-created_at", "-id")[:PAGE]
        return Response(ClaimSerializer(claims, many=True).data)

    def post(self, request, society_id, flat_id):
        flat = get_flat(request, flat_id)
        # Same 404 as a flat that does not exist: nobody learns which flats there are.
        if request.membership.flat_id != flat.id:
            raise NotFound()

        data = ClaimInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        key = request.headers.get("Idempotency-Key")
        if key is not None and not (1 <= len(key) <= 64 and key.isprintable()):
            raise ValidationError({"Idempotency-Key": "Must be 1-64 printable characters."})

        try:
            claim, created = services.submit_claim(
                society=request.society,
                flat=flat,
                claimant=request.user,
                idempotency_key=key,
                **data.validated_data,
            )
        except services.NotYourFlat as exc:
            raise NotFound() from exc
        except services.ClaimExceedsOutstanding as exc:
            raise ValidationError(
                {"amount": f"The flat only owes {exc.outstanding}. Enter an amount up to that."}
            ) from exc
        except services.TooManyPendingClaims as exc:
            return conflict("too_many_pending", str(exc))
        except ledger.IdempotencyKeyReused:
            return conflict(
                "idempotency_key_reused",
                "Idempotency-Key was already used for a different request.",
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(_api_errors(exc)) from exc
        return Response(
            ClaimSerializer(claim).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ClaimListView(SocietyScopedView, APIView):
    """GET /payment-claims/?status=pending|accepted|rejected|withdrawn|all  (office-bearers)."""

    required_capabilities = {"GET": roles.RESOLVE_CLAIM}

    def get(self, request, society_id):
        wanted = request.query_params.get("status", "pending")
        claims = claims_for(request.society)
        if wanted != "all":
            if wanted not in PaymentClaim.Status.values:
                raise ValidationError({"status": "Unknown status."})
            claims = claims.filter(status=wanted)
        return Response(ClaimSerializer(claims.order_by("created_at", "id")[:PAGE], many=True).data)


class ClaimActionView(SocietyScopedView, APIView):
    """Base for the three answers to a claim. The claim is looked up inside the caller's society."""

    def get_claim(self, request, claim_id):
        return get_or_404(claims_for(request.society), claim_id)


class ClaimAcceptView(ClaimActionView):
    """POST /payment-claims/<id>/accept/  body: {amount?, confirm_duplicate?}"""

    required_capabilities = {"POST": roles.RESOLVE_CLAIM}

    def post(self, request, society_id, claim_id):
        claim = self.get_claim(request, claim_id)
        data = AcceptInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            claim = services.accept_claim(
                society=request.society,
                claim=claim,
                actor=request.user,
                amount=data.validated_data.get("amount"),
                confirm_duplicate=data.validated_data["confirm_duplicate"],
            )
        except services.ClaimNotPending as exc:
            return not_pending(exc)
        except ledger.SelfPaymentNotAllowed as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ledger.PaymentExceedsOutstanding as exc:
            raise ValidationError(
                {"amount": f"Exceeds the amount owed ({exc.outstanding})."}
            ) from exc
        except ledger.PossibleDuplicatePayment as exc:
            return conflict(
                "possible_duplicate",
                str(exc),
                previous={
                    "amount": str(exc.previous.amount),
                    "created_at": exc.previous.created_at.isoformat(),
                },
            )
        return Response(ClaimSerializer(claim).data)


class ClaimRejectView(ClaimActionView):
    """POST /payment-claims/<id>/reject/  body: {reason}"""

    required_capabilities = {"POST": roles.RESOLVE_CLAIM}

    def post(self, request, society_id, claim_id):
        claim = self.get_claim(request, claim_id)
        data = RejectInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            claim = services.reject_claim(
                society=request.society,
                claim=claim,
                actor=request.user,
                reason=data.validated_data["reason"],
            )
        except services.ClaimNotPending as exc:
            return not_pending(exc)
        except ledger.SelfPaymentNotAllowed as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(_api_errors(exc)) from exc
        return Response(ClaimSerializer(claim).data)


class ClaimWithdrawView(ClaimActionView):
    """POST /payment-claims/<id>/withdraw/  (only the person who made it)"""

    required_capabilities = {"POST": roles.SUBMIT_CLAIM}

    def post(self, request, society_id, claim_id):
        claim = self.get_claim(request, claim_id)
        if claim.claimed_by_id != request.user.pk:
            raise NotFound()  # someone else's claim is simply not there
        try:
            claim = services.withdraw_claim(
                society=request.society, claim=claim, actor=request.user
            )
        except services.ClaimNotPending as exc:
            return not_pending(exc)
        return Response(ClaimSerializer(claim).data)
