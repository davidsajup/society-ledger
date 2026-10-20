from django.db import IntegrityError
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated

from . import roles
from .models import Flat, Membership
from .permissions import HasCapability, IsSocietyMember
from .serializers import FlatSerializer, MembershipSerializer


class SocietyScopedView:
    """Base for every view under /api/societies/<society_id>/.

    Order matters: IsAuthenticated -> IsSocietyMember (sets request.society) -> HasCapability.
    Subclasses must build querysets from self.request.society via for_society().
    """

    permission_classes = [IsAuthenticated, IsSocietyMember, HasCapability]
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
