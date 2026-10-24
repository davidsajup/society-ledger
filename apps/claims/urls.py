from django.urls import path

from . import views

urlpatterns = [
    path("flats/<int:flat_id>/payment-claims/", views.FlatClaimsView.as_view(), name="flat-claims"),
    path("payment-claims/", views.ClaimListView.as_view(), name="claim-list"),
    path(
        "payment-claims/<int:claim_id>/accept/",
        views.ClaimAcceptView.as_view(),
        name="claim-accept",
    ),
    path(
        "payment-claims/<int:claim_id>/reject/",
        views.ClaimRejectView.as_view(),
        name="claim-reject",
    ),
    path(
        "payment-claims/<int:claim_id>/withdraw/",
        views.ClaimWithdrawView.as_view(),
        name="claim-withdraw",
    ),
]
