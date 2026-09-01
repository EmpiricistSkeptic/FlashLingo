from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, viewsets

from .serializers import UserProgressSerializer

from api.services import stats_service
from .models import UserProgress

def _parse_int_query_param(request, name):
    """
    None if the param is absent; the int value if present and valid;
    raises ValidationError (→ clean 400, not a 500) if present but not a
    valid integer.
    """
    raw = request.query_params.get(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValidationError({name: f"'{raw}' is not a valid integer."})

class ProgressViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only by design — UserProgress rows are only ever created by
    FlashcardViewSet.review(), never directly by the user.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserProgressSerializer

    def get_queryset(self):
        qs = UserProgress.objects.filter(user=self.request.user).order_by("-reviewed_at")

        flashcard_id = self.request.query_params.get("flashcard")
        if flashcard_id is not None:
            qs = qs.filter(flashcard_id=flashcard_id)

        limit = _parse_int_query_param(self.request, "limit")
        if limit is not None:
            qs = qs[: max(1, min(limit, 200))]

        return qs


class StatsOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        language_pair_id = _parse_int_query_param(request, "language_pair")
        return Response(stats_service.get_overview(request.user, language_pair_id))


class LanguageStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(stats_service.get_language_comparison(request.user))


class CategoryStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        language_pair_id = _parse_int_query_param(request, "language_pair")
        if language_pair_id is None:
            return Response(
                {"detail": "language_pair is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(stats_service.get_category_comparison(request.user, language_pair_id))


class DifficultCardsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        language_pair_id = _parse_int_query_param(request, "language_pair")
        category_id = _parse_int_query_param(request, "category")
        limit = _parse_int_query_param(request, "limit") or 10
        return Response(
            stats_service.get_difficult_cards(request.user, language_pair_id, category_id, limit)
        )


class AccuracyTrendView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        language_pair_id = _parse_int_query_param(request, "language_pair")
        days = _parse_int_query_param(request, "days") or 7
        days = max(1, min(days, 90))
        return Response(stats_service.get_accuracy_trend(request.user, language_pair_id, days))