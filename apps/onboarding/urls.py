from django.urls import path

from . import views

urlpatterns = [
    path("societies/", views.SocietyListCreateView.as_view(), name="platform-society-list"),
    path(
        "societies/<int:society_id>/managers/<int:member_id>/reissue/",
        views.ReissueManagerView.as_view(),
        name="platform-manager-reissue",
    ),
]
