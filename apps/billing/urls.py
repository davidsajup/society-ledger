from django.urls import path

from . import views

urlpatterns = [
    path("billing-settings/", views.BillingSettingsView.as_view(), name="billing-settings"),
]
