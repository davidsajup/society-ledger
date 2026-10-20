from django.urls import path

from . import views

urlpatterns = [
    path("flats/<int:flat_id>/payments/", views.PaymentCreateView.as_view(), name="payment-create"),
    path("flats/<int:flat_id>/ledger/", views.FlatLedgerView.as_view(), name="flat-ledger"),
    path(
        "entries/<int:entry_id>/reverse/", views.EntryReverseView.as_view(), name="entry-reverse"
    ),
]
