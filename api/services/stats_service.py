from datetime import datetime, timedelta

from django.db.models import Count, Q, F, FloatField, ExpressionWrapper
from django.db.models.functions import TruncDate
from django.utils import timezone

from api.models import Flashcard, UserProgress, Category, LanguagePair

MIN_REVIEWS_FOR_DIFFICULTY = 3
DIFFICULTY_AGAIN_RATE_THRESHOLD = 0.40


def _accuracy_and_total(progress_qs):
    """
    (accuracy, total_reviews) in a single query. accuracy is None when
    total is 0 rather than dividing by zero. distinct=True on both Count()
    calls is deliberate: progress_qs may be built via a categories__
    language_pair join (a card can sit in more than one category of the
    same pair), which would otherwise duplicate each progress row once
    per matching category and inflate both counts.
    """
    counts = progress_qs.aggregate(
        total=Count("id", distinct=True),
        correct=Count("id", filter=Q(result__in=["good", "easy"]), distinct=True),
    )
    total = counts["total"]
    correct = counts["correct"]
    accuracy = round(correct / total, 4) if total else None
    return accuracy, total


def _compute_streak(user):
    """
    Current + longest streak of distinct calendar days with at least one
    review, across ALL language pairs (per product decision — one streak
    per user, not per pair). "Current" has a one-day grace period: if the
    user reviewed yesterday but hasn't opened the app yet today, the
    streak still counts as alive.

    NOTE: days are computed from reviewed_at as stored (UTC, since
    USE_TZ=True and no per-user timezone exists yet). Revisit if we ever
    store a per-user timezone.
    """
    review_days = set(
        UserProgress.objects.filter(user=user)
        .annotate(day=TruncDate("reviewed_at"))
        .values_list("day", flat=True)
        .distinct()
    )
    if not review_days:
        return {"current": 0, "longest": 0}

    today = timezone.now().date()

    current = 0
    cursor = today if today in review_days else today - timedelta(days=1)
    while cursor in review_days:
        current += 1
        cursor -= timedelta(days=1)

    longest = 0
    streak = 0
    prev_day = None
    for day in sorted(review_days):
        streak = streak + 1 if prev_day and day == prev_day + timedelta(days=1) else 1
        longest = max(longest, streak)
        prev_day = day

    return {"current": current, "longest": longest}


def get_overview(user, language_pair_id=None):
    flashcards_qs = Flashcard.objects.filter(user=user)
    progress_qs = UserProgress.objects.filter(user=user)

    if language_pair_id is not None:
        flashcards_qs = flashcards_qs.filter(
            categories__language_pair_id=language_pair_id
        ).distinct()
        progress_qs = progress_qs.filter(
            flashcard__categories__language_pair_id=language_pair_id
        ).distinct()

    cards = {
        "total": flashcards_qs.count(),
        "new": flashcards_qs.filter(status="new").count(),
        "learning": flashcards_qs.filter(status="learning").count(),
        "learned": flashcards_qs.filter(status="learned").count(),
    }

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    accuracy, total_reviews = _accuracy_and_total(progress_qs)

    reviews = {
        "today": progress_qs.filter(reviewed_at__gte=today_start).count(),
        "week": progress_qs.filter(reviewed_at__gte=week_start).count(),
        "month": progress_qs.filter(reviewed_at__gte=month_start).count(),
        "all_time": total_reviews,
    }

    return {
        "cards": cards,
        "reviews": reviews,
        "accuracy": accuracy,
        "streak": _compute_streak(user),
    }


def get_language_comparison(user):
    """
    One row per language pair. Loops per pair rather than one giant
    annotated query — pair counts are small (a handful per user), so this
    stays simple and readable.
    """
    results = []
    for pair in LanguagePair.objects.filter(user=user):
        flashcards_qs = Flashcard.objects.filter(
            user=user, categories__language_pair=pair
        ).distinct()
        progress_qs = UserProgress.objects.filter(
            user=user, flashcard__categories__language_pair=pair
        ).distinct()

        accuracy, total_reviews = _accuracy_and_total(progress_qs)

        results.append(
            {
                "language_pair_id": pair.id,
                "native": pair.native_language,
                "learning": pair.learning_language,
                "cards": flashcards_qs.count(),
                "accuracy": accuracy,
                "reviews": total_reviews,
            }
        )
    return results


def get_category_comparison(user, language_pair_id):
    results = []
    for category in Category.objects.filter(user=user, language_pair_id=language_pair_id):
        # A single Category, not a language_pair join — no M2M duplication
        # risk here, so no .distinct() needed on either queryset.
        flashcards_qs = Flashcard.objects.filter(user=user, categories=category)
        progress_qs = UserProgress.objects.filter(user=user, flashcard__categories=category)

        accuracy, _ = _accuracy_and_total(progress_qs)

        results.append(
            {
                "category_id": category.id,
                "name": category.name,
                "cards": flashcards_qs.count(),
                "accuracy": accuracy,
            }
        )
    return results


def get_difficult_flashcards(
    user,
    language_pair_id=None,
    category_id=None,
    limit=20,
):
    """
    Returns actual flashcards that are genuinely difficult for the user.

    A card is considered difficult when:
    - it has enough review history;
    - at least 40% of its reviews were rated "again".

    The deck is dynamic and is not stored in the database.
    """

    flashcards_qs = Flashcard.objects.filter(
        user=user,
    )

    if category_id is not None:
        flashcards_qs = flashcards_qs.filter(
            categories__id=category_id,
        )

    elif language_pair_id is not None:
        flashcards_qs = flashcards_qs.filter(
            categories__language_pair_id=language_pair_id,
        )

    flashcards_qs = (
        flashcards_qs
        .annotate(
            progress_count=Count(
                "progress",
                distinct=True,
            ),
            again_count=Count(
                "progress",
                filter=Q(
                    progress__result="again"
                ),
                distinct=True,
            ),
        )
        .filter(
            progress_count__gte=MIN_REVIEWS_FOR_DIFFICULTY,
        )
        .annotate(
            again_rate=ExpressionWrapper(
                F("again_count") * 1.0 / F("progress_count"),
                output_field=FloatField(),
            )
        )
        .filter(
            again_rate__gte=DIFFICULTY_AGAIN_RATE_THRESHOLD,
        )
        .order_by(
            "-again_rate",
            "-progress_count",
            "id",
        )
    )

    return flashcards_qs[:limit]

def get_difficult_cards(user, language_pair_id=None, category_id=None, limit=10):
    """
    Cards sorted by their "again" rate, restricted to cards with enough
    review history to be meaningful (MIN_REVIEWS_FOR_DIFFICULTY).
    """
    flashcards = get_difficult_flashcards(
        user=user,
        language_pair_id=language_pair_id,
        category_id=category_id,
        limit=limit,
    )

    return [
        {
            "flashcard_id": card.id,
            "text": card.text,
            "reviews": card.progress_count,
            "again_rate": round(card.again_rate, 4),
            "ease_factor": card.ease_factor,
        }
        for card in flashcards
    ]


def get_accuracy_trend(user, language_pair_id=None, days=7):
    """
    Per-day {date, accuracy, reviews} for the last `days` calendar days
    (inclusive of today), ordered oldest-first — feeds a simple line/bar
    chart of accuracy over time. Days with zero reviews get
    accuracy=None (not 0) so the frontend can distinguish "no data" from
    "reviewed everything wrong that day".
    """
    today = timezone.now().date()
    start_date = today - timedelta(days=days - 1)
    start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))

    progress_qs = UserProgress.objects.filter(user=user, reviewed_at__gte=start_datetime)
    if language_pair_id is not None:
        progress_qs = progress_qs.filter(
            flashcard__categories__language_pair_id=language_pair_id
        )

    # Same duplication risk as elsewhere when joining through
    # categories__language_pair — distinct=True guards against it.
    daily = (
        progress_qs.annotate(day=TruncDate("reviewed_at"))
        .values("day")
        .annotate(
            total=Count("id", distinct=True),
            correct=Count("id", filter=Q(result__in=["good", "easy"]), distinct=True),
        )
    )
    by_day = {row["day"]: row for row in daily}

    trend = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        row = by_day.get(day)
        if row and row["total"]:
            accuracy = round(row["correct"] / row["total"], 4)
            reviews = row["total"]
        else:
            accuracy = None
            reviews = 0
        trend.append({"date": day.isoformat(), "accuracy": accuracy, "reviews": reviews})

    return trend

