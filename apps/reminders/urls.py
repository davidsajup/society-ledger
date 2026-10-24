from django.urls import path

from . import views

urlpatterns = [
    path(
        "dues-reminders/preview/",
        views.ReminderPreviewView.as_view(),
        name="reminder-preview",
    ),
    path("dues-reminders/", views.ReminderSendView.as_view(), name="reminder-send"),
]
