import re

from django.shortcuts import get_object_or_404

from ...models import Flashcard, GameAttempt


_PUNCTUATION_EDGE = (
    ".,!?;:¡¿\"'“”‘’«»"
)


def _normalize(value: str) -> str:
    value = value.strip().casefold()

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    value = value.strip(
        _PUNCTUATION_EDGE
    )

    return value


def evaluate_typing(
    *,
    user,
    flashcard_id: int,
    answer: str,
) -> GameAttempt:

    flashcard = get_object_or_404(
        Flashcard,
        id=flashcard_id,
        user=user,
    )

    normalized_answer = _normalize(answer)
    expected_answer = _normalize(flashcard.text)

    is_correct = (
        bool(normalized_answer)
        and normalized_answer == expected_answer
    )

    return GameAttempt.objects.create(
        user=user,
        flashcard=flashcard,
        game_type="typing",
        is_correct=is_correct,
        user_answer=answer,
        score=None,
    )

def give_up_typing(
    *,
    user,
    flashcard_id: int,
) -> GameAttempt:
    """
    Logs a "show answer" action as a failed attempt. No comparison
    is made — the user never submitted an answer to evaluate.
    """

    flashcard = get_object_or_404(
        Flashcard,
        id=flashcard_id,
        user=user,
    )

    return GameAttempt.objects.create(
        user=user,
        flashcard=flashcard,
        game_type="typing",
        is_correct=False,
        user_answer="",
        gave_up=True,
        score=None,
    )