from django.shortcuts import get_object_or_404

from ...models import Flashcard, GameAttempt

from ..deepseek_service import (
    AIServiceError,
    DeepSeekService,
)

from . import prompts
from ._language import (
    get_language_pair_for,
    language_names,
)


def _clean_translations(
    flashcard,
) -> list[str]:

    if not isinstance(
        flashcard.translations,
        list,
    ):
        return []

    return [
        item.strip()
        for item
        in flashcard.translations
        if isinstance(item, str)
        and item.strip()
    ]


def _validate_generation_result(
    result: dict,
) -> dict:

    context = result.get(
        "context"
    )

    instruction = result.get(
        "instruction"
    )

    if not isinstance(
        context,
        str,
    ) or not context.strip():

        raise AIServiceError(
            "AI returned invalid sentence context."
        )

    if not isinstance(
        instruction,
        str,
    ) or not instruction.strip():

        raise AIServiceError(
            "AI returned invalid sentence instruction."
        )

    return {
        "context": context.strip(),
        "instruction": instruction.strip(),
    }


def _validate_evaluation_result(
    result: dict,
) -> dict:

    is_correct = result.get(
        "is_correct"
    )

    score = result.get(
        "score"
    )

    feedback = result.get(
        "feedback"
    )

    correction = result.get(
        "correction"
    )

    # IMPORTANT:
    # bool only — not "true"/"false".
    if not isinstance(
        is_correct,
        bool,
    ):
        raise AIServiceError(
            "AI returned invalid is_correct value."
        )

    if (
        not isinstance(
            score,
            (int, float),
        )
        or isinstance(score, bool)
    ):
        raise AIServiceError(
            "AI returned invalid score."
        )

    score = float(score)

    if not 0.0 <= score <= 1.0:
        raise AIServiceError(
            "AI returned score outside 0..1."
        )

    if not isinstance(
        feedback,
        str,
    ) or not feedback.strip():

        raise AIServiceError(
            "AI returned invalid feedback."
        )

    if (
        correction is not None
        and not isinstance(
            correction,
            str,
        )
    ):
        raise AIServiceError(
            "AI returned invalid correction."
        )

    if (
        isinstance(correction, str)
        and not correction.strip()
    ):
        correction = None

    return {
        "is_correct": is_correct,
        "score": score,
        "feedback": feedback.strip(),
        "correction": (
            correction.strip()
            if isinstance(correction, str)
            else None
        ),
    }


def generate_sentence_challenge(
    *,
    user,
    flashcard_id: int,
) -> dict:

    flashcard = get_object_or_404(
        Flashcard,
        id=flashcard_id,
        user=user,
    )

    language_pair = get_language_pair_for(
        flashcard
    )

    learning_language, native_language = (
        language_names(language_pair)
    )

    translations = _clean_translations(
        flashcard
    )

    if not translations:
        raise ValueError(
            "Flashcard has no valid translations."
        )

    target_word = flashcard.text.strip()

    if not target_word:
        raise ValueError(
            "Flashcard has no target word."
        )

    system_prompt, user_prompt = (
        prompts.sentence_generation_prompt(
            target_word=target_word,
            translations=translations,
            learning_language=learning_language,
            native_language=native_language,
        )
    )

    ai = DeepSeekService()

    result = ai.generate_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=300,
        temperature=0.5,
    )

    result = _validate_generation_result(
        result
    )

    return {
        "game_type": "sentence",
        "flashcard_id": flashcard.id,
        "context": result["context"],
        "instruction": result["instruction"],
    }


def evaluate_sentence_challenge(
    *,
    user,
    flashcard_id: int,
    context: str,
    answer: str,
) -> tuple[GameAttempt, dict]:

    flashcard = get_object_or_404(
        Flashcard,
        id=flashcard_id,
        user=user,
    )

    language_pair = get_language_pair_for(
        flashcard
    )

    learning_language, _native_language = (
        language_names(language_pair)
    )

    target_word = flashcard.text.strip()

    if not target_word:
        raise ValueError(
            "Flashcard has no target word."
        )

    system_prompt, user_prompt = (
        prompts.sentence_evaluation_prompt(
            target_word=target_word,
            context=context,
            user_sentence=answer,
            learning_language=learning_language,
        )
    )

    ai = DeepSeekService()

    result = ai.generate_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=400,
        temperature=0.2,
    )

    evaluation = _validate_evaluation_result(
        result
    )

    attempt = GameAttempt.objects.create(
        user=user,
        flashcard=flashcard,
        game_type="sentence",
        is_correct=evaluation[
            "is_correct"
        ],
        user_answer=answer,
        score=evaluation[
            "score"
        ],
    )

    return attempt, evaluation