from django.urls import path

from . import views

urlpatterns = [
    path("flats/", views.FlatListCreateView.as_view(), name="flat-list"),
    path("flats/<int:pk>/", views.FlatDetailView.as_view(), name="flat-detail"),
    path("members/", views.MembershipListCreateView.as_view(), name="member-list"),
]
