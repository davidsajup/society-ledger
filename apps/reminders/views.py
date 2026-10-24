from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.societies import roles
from apps.societies.views import SocietyScopedView

from . import services


class ReminderPreviewView(SocietyScopedView, APIView):
    """GET /dues-reminders/preview/  Counts only: how many flats owe and how many can be emailed."""

    required_capabilities = {"GET": roles.SEND_REMINDERS}

    def get(self, request, society_id):
        response = Response(services.preview(request.society))
        response["Cache-Control"] = "no-store"
        return response


class ReminderSendView(SocietyScopedView, APIView):
    """POST /dues-reminders/  Email every flat that owes and was not reminded this week."""

    required_capabilities = {"POST": roles.SEND_REMINDERS}
    throttle_scope = "reminder"

    def get_throttles(self):
        return [ScopedRateThrottle()]

    def post(self, request, society_id):
        result = services.send_dues_reminders(society=request.society, actor=request.user)
        response = Response(result)
        response["Cache-Control"] = "no-store"
        return response
