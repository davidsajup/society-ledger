from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .demo import demo_accounts, demo_enabled, demo_users
from .serializers import DemoLoginSerializer, LoginSerializer, serialize_me


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
