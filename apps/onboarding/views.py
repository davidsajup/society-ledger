from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Prefetch
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.societies import roles
from apps.societies.models import Membership, Society
from apps.societies.serializers import _api_errors
from apps.societies.services import (
    CredentialsNotAllowed,
    create_society,
    reissue_manager_credentials,
)

from .permissions import IsPlatformAdmin
from .serializers import CreateSocietySerializer, ManagerSerializer


def _credentials(user, temporary_password, **extra):
    """The ONE response that carries a temporary password. Never cache it."""
    response = Response(
        {
            "username": user.username,
            "temp_password": temporary_password,
            "expires_at": user.temp_password_expires_at,
            **extra,
        }
    )
    response["Cache-Control"] = "no-store"
    return response


def _society_row(society):
    return {
        "id": society.id,
        "name": society.name,
        "slug": society.slug,
        "created_at": society.created_at,
        "billing_cycle_months": society.billing_cycle_months,
        "billing_start": society.billing_start,
        "flat_count": society.flat_count,
        "member_count": society.member_count,
        "managers": ManagerSerializer(society.managers, many=True).data,
    }


class PlatformView:
    permission_classes = [IsPlatformAdmin]


class SocietyListCreateView(PlatformView, APIView):
    """GET /api/platform/societies/ and POST to onboard a new one.

    The list holds counts and the president/secretary logins only: no balances, no payments.
    """

    def get(self, request):
        managers = Membership.objects.filter(role__in=roles.roles_with(roles.MANAGE_MEMBERS))
        societies = (
            Society.objects.annotate(
                flat_count=Count("flats", distinct=True),
                member_count=Count("memberships", distinct=True),
            )
            .prefetch_related(
                Prefetch(
                    "memberships",
                    queryset=managers.select_related("user").order_by("id"),
                    to_attr="managers",
                )
            )
            .order_by("name")
        )
        return Response([_society_row(s) for s in societies])

    def post(self, request):
        data = CreateSocietySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            society, membership, temporary_password = create_society(
                actor=request.user, **data.validated_data
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(_api_errors(exc)) from exc
        response = _credentials(
            membership.user,
            temporary_password,
            society={"id": society.id, "name": society.name, "slug": society.slug},
            president_name=membership.user.first_name,
        )
        response.status_code = status.HTTP_201_CREATED
        return response


class ReissueManagerView(PlatformView, APIView):
    """POST /api/platform/societies/<id>/managers/<member_id>/reissue/: a lost president login."""

    def post(self, request, society_id, member_id):
        membership = (
            Membership.objects.filter(pk=member_id, society_id=society_id)
            .select_related("user", "society")
            .first()
        )
        if membership is None:
            raise NotFound()
        try:
            temporary_password = reissue_manager_credentials(
                actor=request.user, membership=membership
            )
        except CredentialsNotAllowed as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return _credentials(membership.user, temporary_password)
