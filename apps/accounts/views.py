from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .credentials import temp_password_expired
from .demo import demo_accounts, demo_enabled, demo_users
from .serializers import (
    ChangePasswordSerializer,
    DemoLoginSerializer,
    LoginSerializer,
    serialize_me,
)


class CsrfView(APIView):
    """Hands the SPA a CSRF token (also sets the csrftoken cookie)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class LoginView(APIView):
    # No authentication classes: a login request has no session yet, so there is nothing for
    # CSRF to protect. Brute force is the real risk here, hence the throttle.
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            # Same message for unknown user and wrong password: no username enumeration.
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_400_BAD_REQUEST)
        if temp_password_expired(user):
            # Only reachable with the CORRECT password, so this does not reveal which
            # usernames exist. An expired temporary password never creates a session.
            return Response(
                {
                    "detail": "This temporary password has expired. Ask your admin for a new one.",
                    "code": "credentials_expired",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request, user)
        return Response(serialize_me(user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(serialize_me(request.user))


class DemoInfoView(APIView):
    """Is demo mode on, and which one-click accounts exist? Public, and reveals no secrets."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        if not demo_enabled():
            return Response({"enabled": False, "accounts": []})
        return Response({"enabled": True, "accounts": demo_accounts()})


class DemoLoginView(APIView):
    """Log in as an allowlisted demo user without a password. 404 unless demo mode is on."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "demo"

    def post(self, request):
        if not demo_enabled():
            raise NotFound()
        serializer = DemoLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # demo_users() is the single gate: allowlisted, active, and never staff or superuser.
        user = demo_users().filter(username=serializer.validated_data["username"]).first()
        if user is None:
            raise NotFound()  # same answer for "not on the list" and "does not exist"
        user.backend = "django.contrib.auth.backends.ModelBackend"  # login() needs to know
        login(request, user)
        return Response(serialize_me(user))


class ChangePasswordView(APIView):
    """POST /auth/change-password/: choose a new password.

    Deliberately NOT IsSettledUser: this is the one write a person on a temporary password
    is allowed to make, because it is how they stop being one.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password"

    def post(self, request):
        data = ChangePasswordSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        current = data.validated_data["current_password"]
        new = data.validated_data["new_password"]
        user = request.user

        if not user.check_password(current):
            raise ValidationError({"current_password": ["Your current password is incorrect."]})
        if new == current:
            raise ValidationError(
                {"new_password": ["Choose a password different from the old one."]}
            )
        try:
            validate_password(new, user)  # Django's validators: length, common, numeric, similar
        except DjangoValidationError as exc:
            raise ValidationError({"new_password": list(exc.messages)}) from exc

        user.set_password(new)
        user.must_change_password = False
        user.temp_password_expires_at = None
        user.save(update_fields=["password", "must_change_password", "temp_password_expires_at"])
        update_session_auth_hash(request, user)  # keep THIS session; every other one dies
        return Response(serialize_me(user))
