from django.urls import path

from . import views

urlpatterns = [
    path("imports/preview/", views.ImportPreviewView.as_view(), name="import-preview"),
    path("imports/confirm/", views.ImportConfirmView.as_view(), name="import-confirm"),
]
