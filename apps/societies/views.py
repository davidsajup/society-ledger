from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import generics, serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsSettledUser

from . import roles
from .models import Flat, Membership
from .permissions import HasCapability, IsSocietyMember
from .serializers import (
    CreateLoginSerializer,
    FlatSerializer,
    MembershipSerializer,
    _api_errors,
)
from .services import CredentialsNotAllowed, create_member_login, reissue_credentials


class SocietyScopedView:
    """Base for every view under /api/societies/<society_id>/.

    Order matters: IsSettledUser -> IsSocietyMember (sets request.society) -> HasCapability.
    Subclasses must build querysets from self.request.society via for_society().
    """

    permission_classes = [IsSettledUser, IsSocietyMember, HasCapability]
    required_capabilities: dict = {}

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "society": self.request.society}


class FlatListCreateView(SocietyScopedView, generics.ListCreateAPIView):
    serializer_class = FlatSerializer
    required_capabilities = {"GET": roles.VIEW_FLATS, "POST": roles.MANAGE_FLATS}

    def get_queryset(self):
        return Flat.objects.for_society(self.request.society).order_by("label")

    def perform_create(self, serializer):
        try:
            serializer.save(society=self.request.society)
        except IntegrityError:
            # Lost a race with a concurrent create: the DB constraint is the backstop.
            raise serializers.ValidationError(
                {"label": "A flat with this label already exists."}
            ) from None


class FlatDetailView(SocietyScopedView, generics.RetrieveUpdateAPIView):
    serializer_class = FlatSerializer
    http_method_names = ["get", "patch", "head", "options"]
    required_capabilities = {"GET": roles.VIEW_FLATS, "PATCH": roles.MANAGE_FLATS}

    def get_queryset(self):
        # A flat id from another society is simply "not in this queryset" -> 404.
        return Flat.objects.for_society(self.request.society)


class MembershipListCreateView(SocietyScopedView, generics.ListCreateAPIView):
    serializer_class = MembershipSerializer
    required_capabilities = {"GET": roles.MANAGE_MEMBERS, "POST": roles.MANAGE_MEMBERS}

    def get_queryset(self):
        # select_related avoids one extra query per row (N+1) when serializing user and flat.
        return (
            Membership.objects.for_society(self.request.society)
            .select_related("user", "flat")
            .order_by("id")
        )


def _credentials_response(user, temporary_password, **extra):
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


class CreateLoginView(SocietyScopedView, APIView):
    """POST /people/ (admin): create a brand-new login with a one-time temporary password."""

    required_capabilities = {"POST": roles.MANAGE_MEMBERS}

    def post(self, request, society_id):
        data = CreateLoginSerializer(data=request.data, context={"society": request.society})
        data.is_valid(raise_exception=True)
        try:
            membership, temporary_password = create_member_login(
                society=request.society,
                actor=request.user,
                name=data.validated_data["name"],
                role=data.validated_data["role"],
                flat=data.validated_data.get("flat"),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(_api_errors(exc)) from exc
        except IntegrityError:
            raise serializers.ValidationError(
                {"name": ["Could not create a unique username. Please try again."]}
            ) from None
        response = _credentials_response(
            membership.user,
            temporary_password,
            member=MembershipSerializer(membership, context={"society": request.society}).data,
        )
        response.status_code = status.HTTP_201_CREATED
        return response


class ReissueCredentialsView(SocietyScopedView, APIView):
    """POST /members/<id>/reissue/ (admin): new temporary password for one member."""

    required_capabilities = {"POST": roles.MANAGE_MEMBERS}

    def post(self, request, society_id, member_id):
        membership = (
            Membership.objects.for_society(request.society)
            .select_related("user", "flat")
            .filter(pk=member_id)
            .first()
        )
        if membership is None:
            raise NotFound()  # another society's member id looks exactly like a missing one
        try:
            temporary_password = reissue_credentials(
                society=request.society, actor=request.user, membership=membership
            )
        except CredentialsNotAllowed as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return _credentials_response(membership.user, temporary_password)
