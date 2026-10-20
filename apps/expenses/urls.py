from django.urls import path

from . import views

urlpatterns = [
    path("expenses/", views.ExpenseListCreateView.as_view(), name="expense-list"),
    path(
        "expenses/<int:expense_id>/reverse/",
        views.ExpenseReverseView.as_view(),
        name="expense-reverse",
    ),
]
