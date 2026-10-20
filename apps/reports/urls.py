from django.urls import path

from . import views

urlpatterns = [
    path("summary/", views.SummaryView.as_view(), name="summary"),
    path("activity/", views.ActivityView.as_view(), name="activity"),
]
