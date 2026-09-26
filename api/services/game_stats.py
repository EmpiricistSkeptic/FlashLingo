from datetime import datetime, timedelta

from django.db.models import Avg
from django.utils import timezone

from ..models import GameAttempt


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


def get_game_overview(user):
    attempts = GameAttempt.objects.filter(
        user=user,
    )

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

    success_rate = 0.0

    if answered_attempts:
        success_rate = round(
            successful_attempts
            / answered_attempts
            * 100,
            1,
        )

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


def get_game_modes(user):
    attempts = GameAttempt.objects.filter(
        user=user,
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

        success_rate = 0.0

        if answered:
            success_rate = round(
                correct / answered * 100,
                1,
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


def get_game_skills(user):
    mode_stats = {
        item["game_type"]: item
        for item in get_game_modes(user)
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

    attempts = (
        GameAttempt.objects
        .filter(
            user=user,
            created_at__gte=start_datetime,
        )
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
):
    limit = max(
        1,
        min(limit, 50),
    )

    attempts = (
        GameAttempt.objects
        .filter(user=user)
        .only(
            "id",
            "game_type",
            "is_correct",
            "gave_up",
            "score",
            "feedback",
            "created_at",
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
            "created_at": attempt.created_at.isoformat(),
        }
        for attempt in attempts
    ]