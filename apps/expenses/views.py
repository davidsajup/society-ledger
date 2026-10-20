from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.societies import roles
from apps.societies.views import SocietyScopedView

from . import services
from .models import Expense
from .selectors import total_spent
from .serializers import ExpenseInputSerializer, ExpenseListSerializer, ExpenseSerializer

LIST_PAGE = 200  # newest expenses returned; real pagination can come when there are more


class ExpenseListCreateView(SocietyScopedView, APIView):
    """GET /expenses/ (office-bearers); POST /expenses/ (treasurer). Header: Idempotency-Key."""

    required_capabilities = {"GET": roles.VIEW_EXPENSES, "POST": roles.RECORD_EXPENSE}

    def get(self, request, society_id):
        expenses = (
            Expense.objects.for_society(request.society)
            .select_related("created_by")
            .order_by("-paid_on", "-id")[:LIST_PAGE]
        )
        payload = {"total_spent": total_spent(request.society), "expenses": expenses}
        return Response(ExpenseListSerializer(payload).data)

    def post(self, request, society_id):
        data = ExpenseInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)

        key = request.headers.get("Idempotency-Key")
        if key is not None and not (1 <= len(key) <= 64 and key.isprintable()):
            raise ValidationError({"Idempotency-Key": "Must be 1-64 printable characters."})

        try:
            expense, created = services.record_expense(
                society=request.society,
                actor=request.user,
                idempotency_key=key,
                **data.validated_data,
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        except services.IdempotencyKeyReused:
            return Response(
                {"detail": "Idempotency-Key was already used for a different request."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            ExpenseSerializer(expense).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ExpenseReverseView(SocietyScopedView, APIView):
    """POST /expenses/<expense_id>/reverse/ (treasurer)."""

    required_capabilities = {"POST": roles.RECORD_EXPENSE}

    def post(self, request, society_id, expense_id):
        expense = Expense.objects.for_society(request.society).filter(pk=expense_id).first()
        if expense is None:
            raise NotFound()  # same body for missing and other-society ids
        try:
            reversal = services.reverse_expense(
                society=request.society, expense=expense, actor=request.user
            )
        except services.ExpenseNotReversible as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(ExpenseSerializer(reversal).data, status=status.HTTP_201_CREATED)
