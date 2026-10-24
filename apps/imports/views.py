from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.societies import roles
from apps.societies.roles import role_can
from apps.societies.views import SocietyScopedView

from .parsing import MAX_FILE_BYTES, ImportFileError, read_rows
from .serializers import ConfirmImportSerializer
from .services import ImportInvalid, clean_rows, import_flats_and_people, summarize


class ImportView(SocietyScopedView, APIView):
    """Base: president and secretary only, throttled, and never cached (the data is personal).

    An import creates flats AND people, so the caller needs both capabilities. The capability
    table gives them to the same two roles today; checking both keeps it true if that changes.
    """

    required_capabilities = {"POST": roles.MANAGE_MEMBERS}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "import"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not role_can(request.membership.role, roles.MANAGE_FLATS):
            raise PermissionDenied()

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response


class ImportPreviewView(ImportView):
    """POST /imports/preview/ (multipart, field `file`): read and check a file. Writes NOTHING."""

    parser_classes = [MultiPartParser]

    def post(self, request, society_id):
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {"file": ["Choose a file to upload."]}, status=status.HTTP_400_BAD_REQUEST
            )
        if upload.size > MAX_FILE_BYTES:
            return Response(
                {"file": ["The file is larger than 1 MB. A flats list should be far smaller."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            parsed = read_rows(upload.name, upload.read())
        except ImportFileError as exc:
            return Response({"file": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

        raw = [{"row": number, **values} for number, values in parsed.rows]
        clean, errors = clean_rows(request.society, raw)
        return Response(
            {
                "rows": clean,
                "errors": errors,
                "ignored_columns": parsed.ignored_columns,
                "summary": summarize(clean),
                "cycle_months": request.society.billing_cycle_months,
            }
        )


class ImportConfirmView(ImportView):
    """POST /imports/confirm/ (JSON rows): create everything, or nothing. Returns the logins.

    The rows come from the client, so they are checked again from scratch, inside a lock.
    The response is the only time the temporary passwords exist in plain text.
    """

    parser_classes = [JSONParser]

    def post(self, request, society_id):
        data = ConfirmImportSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            result = import_flats_and_people(
                society=request.society, actor=request.user, rows=data.validated_data["rows"]
            )
        except ImportInvalid as exc:
            return Response({"errors": exc.errors}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError:
            return Response(
                {
                    "detail": "Another change happened at the same moment. Please upload again."
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(result, status=status.HTTP_201_CREATED)
