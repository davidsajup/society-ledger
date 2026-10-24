from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/platform/", include("apps.onboarding.urls")),
    path("api/societies/<int:society_id>/", include("apps.societies.urls")),
    path("api/societies/<int:society_id>/", include("apps.ledger.urls")),
    path("api/societies/<int:society_id>/", include("apps.expenses.urls")),
    path("api/societies/<int:society_id>/", include("apps.audit.urls")),
    path("api/societies/<int:society_id>/", include("apps.reports.urls")),
    path("api/societies/<int:society_id>/", include("apps.imports.urls")),
    path("api/societies/<int:society_id>/", include("apps.billing.urls")),
]
