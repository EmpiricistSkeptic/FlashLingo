from datetime import datetime, timedelta

from django.db.models import Avg
from django.utils import timezone

from ..models import GameAttempt, LanguagePair


GAME_TYPES = (
    "typing",
    "sentence",
    "translation",
)

AI_GAME_TYPES = (
    "sentence",
    "translation",
)


def _percentage(
    value: float | None,
) -> float | None:
    if value is None:
        return None

    return round(
        value * 100,
        1,
    )


def _success_rate(attempts) -> float:
    answered_count = attempts.filter(
        gave_up=False,
    ).count()

    if answered_count == 0:
        return 0.0

    correct_count = attempts.filter(
        gave_up=False,
        is_correct=True,
    ).count()

    return round(
        correct_count / answered_count * 100,
        1,
    )


def _filter_by_language_pair(
    attempts,
    language_pair_id,
):
    """
    Flashcard has no direct FK to LanguagePair — the link goes through
    the categories M2M (Flashcard.categories -> Category.language_pair).
    A single flashcard can sit in more than one Category of the same
    pair, so this join can duplicate GameAttempt rows the same way it
    does for UserProgress in the Learning stats service — .distinct()
    guards against that, same reasoning as _accuracy_and_total there.
    """

    if language_pair_id is None:
        return attempts

    return attempts.filter(
        flashcard__categories__language_pair_id=(
            language_pair_id
        ),
    ).distinct()


def _overview_stats(attempts) -> dict:
    """
    Shared by get_game_overview (all attempts for the user) and
    get_game_language_comparison (attempts scoped to one pair) — same
    six numbers, computed from whatever GameAttempt queryset is handed
    in.
    """

    total_attempts = attempts.count()

    give_up_attempts = attempts.filter(
        gave_up=True,
    ).count()

    answered_attempts = attempts.filter(
        gave_up=False,
    ).count()

    successful_attempts = attempts.filter(
        gave_up=False,
        is_correct=True,
    ).count()

    average_ai_score = (
        attempts
        .filter(
            game_type__in=AI_GAME_TYPES,
            gave_up=False,
            score__isnull=False,
        )
        .aggregate(
            average=Avg("score"),
        )
        ["average"]
    )

    success_rate = _success_rate(attempts)

    give_up_rate = 0.0

    if total_attempts:
        give_up_rate = round(
            give_up_attempts
            / total_attempts
            * 100,
            1,
        )

    return {
        "total_attempts": total_attempts,
        "answered_attempts": answered_attempts,
        "successful_attempts": successful_attempts,
        "success_rate": success_rate,
        "give_up_attempts": give_up_attempts,
        "give_up_rate": give_up_rate,
        "average_ai_score": _percentage(
            average_ai_score
        ),
    }


def get_game_overview(
    user,
    language_pair_id=None,
):
    attempts = _filter_by_language_pair(
        GameAttempt.objects.filter(
            user=user,
        ),
        language_pair_id,
    )

    return _overview_stats(attempts)


def get_game_language_comparison(user):
    """
    One row per language pair the user has, mirroring
    get_language_comparison in the Learning stats service. Loops per
    pair rather than one giant annotated query — same reasoning as the
    Learning-side version: pair counts are small per user, so this
    stays simple and readable.
    """

    results = []

    for pair in LanguagePair.objects.filter(
        user=user,
    ):
        attempts = (
            GameAttempt.objects
            .filter(user=user)
            .filter(
                flashcard__categories__language_pair=pair,
            )
            .distinct()
        )

        stats = _overview_stats(attempts)

        results.append(
            {
                "language_pair_id": pair.id,
                "native": pair.native_language,
                "learning": pair.learning_language,
                **stats,
            }
        )

    return results


def get_game_modes(
    user,
    language_pair_id=None,
):
    attempts = _filter_by_language_pair(
        GameAttempt.objects.filter(
            user=user,
        ),
        language_pair_id,
    )

    result = []

    for game_type in GAME_TYPES:
        mode_attempts = attempts.filter(
            game_type=game_type,
        )

        count = mode_attempts.count()

        answered = mode_attempts.filter(
            gave_up=False,
        ).count()

        correct = mode_attempts.filter(
            gave_up=False,
            is_correct=True,
        ).count()

        success_rate = _success_rate(
            mode_attempts
        )

        average_ai_score = None

        if game_type in AI_GAME_TYPES:
            average_ai_score = (
                mode_attempts
                .filter(
                    gave_up=False,
                    score__isnull=False,
                )
                .aggregate(
                    average=Avg("score"),
                )
                ["average"]
            )

            average_ai_score = _percentage(
                average_ai_score
            )

        result.append(
            {
                "game_type": game_type,
                "attempts": count,
                "answered_attempts": answered,
                "successful_attempts": correct,
                "success_rate": success_rate,
                "average_ai_score": average_ai_score,
            }
        )

    return result


def get_game_skills(
    user,
    language_pair_id=None,
):
    mode_stats = {
        item["game_type"]: item
        for item in get_game_modes(
            user,
            language_pair_id=language_pair_id,
        )
    }

    typing_stats = mode_stats["typing"]
    sentence_stats = mode_stats["sentence"]
    translation_stats = mode_stats["translation"]

    return [
        {
            "skill": "recall",
            "label": "Recall",
            "game_type": "typing",
            "performance": (
                typing_stats["success_rate"]
                if typing_stats["attempts"] > 0
                else None
            ),
        },
        {
            "skill": "sentence_usage",
            "label": "Sentence Usage",
            "game_type": "sentence",
            "performance": (
                sentence_stats["average_ai_score"]
                if sentence_stats["attempts"] > 0
                else None
            ),
        },
        {
            "skill": "translation",
            "label": "Translation",
            "game_type": "translation",
            "performance": (
                translation_stats["average_ai_score"]
                if translation_stats["attempts"] > 0
                else None
            ),
        },
    ]


def get_game_trend(
    user,
    days: int = 14,
    language_pair_id=None,
):
    if days < 1:
        days = 1

    today = timezone.localdate()

    start_date = today - timedelta(
        days=days - 1
    )

    start_datetime = timezone.make_aware(
        datetime.combine(
            start_date,
            datetime.min.time(),
        )
    )

    attempts = _filter_by_language_pair(
        GameAttempt.objects.filter(
            user=user,
            created_at__gte=start_datetime,
        ),
        language_pair_id,
    )

    attempts = (
        attempts
        .only(
            "game_type",
            "is_correct",
            "gave_up",
            "score",
            "created_at",
        )
        .order_by("created_at")
    )

    buckets = {}

    for index in range(days):
        current_date = (
            start_date
            + timedelta(days=index)
        )

        buckets[current_date] = {
            "attempts": 0,
            "values": [],
        }

    for attempt in attempts:
        local_date = timezone.localtime(
            attempt.created_at
        ).date()

        bucket = buckets.get(
            local_date
        )

        if bucket is None:
            continue

        bucket["attempts"] += 1

        # Give-ups are included in the attempt count,
        # but excluded from performance.
        if attempt.gave_up:
            continue

        if attempt.game_type == "typing":
            value = (
                1.0
                if attempt.is_correct
                else 0.0
            )

        elif (
            attempt.game_type in AI_GAME_TYPES
            and attempt.score is not None
        ):
            value = max(
                0.0,
                min(1.0, attempt.score),
            )

        else:
            continue

        bucket["values"].append(value)

    result = []

    for current_date, bucket in buckets.items():
        values = bucket["values"]

        performance = None

        if values:
            performance = round(
                sum(values)
                / len(values)
                * 100,
                1,
            )

        result.append(
            {
                "date": current_date.isoformat(),
                "attempts": bucket["attempts"],
                "performance": performance,
            }
        )

    return result


def get_recent_game_activity(
    user,
    limit: int = 8,
    language_pair_id=None,
):
    limit = max(
        1,
        min(limit, 50),
    )

    attempts = _filter_by_language_pair(
        GameAttempt.objects.filter(
            user=user,
        ),
        language_pair_id,
    )

    attempts = (
        attempts
        .select_related("flashcard")
        .only(
            "id",
            "game_type",
            "is_correct",
            "gave_up",
            "score",
            "feedback",
            "created_at",
            "flashcard__text",
        )
        .order_by("-created_at")[:limit]
    )

    return [
        {
            "id": attempt.id,
            "game_type": attempt.game_type,
            "is_correct": attempt.is_correct,
            "gave_up": attempt.gave_up,
            "score": (
                round(
                    attempt.score * 100,
                    1,
                )
                if attempt.score is not None
                else None
            ),
            "feedback": attempt.feedback,
            "flashcard_text": (
                attempt.flashcard.text
            ),
            "created_at": attempt.created_at.isoformat(),
        }
        for attempt in attempts
    ]