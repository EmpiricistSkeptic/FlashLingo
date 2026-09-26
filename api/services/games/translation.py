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

    source_sentence = result.get(
        "source_sentence"
    )

    instruction = result.get(
        "instruction"
    )

    if not isinstance(
        source_sentence,
        str,
    ) or not source_sentence.strip():

        raise AIServiceError(
            "AI returned invalid source sentence."
        )

    if not isinstance(
        instruction,
        str,
    ) or not instruction.strip():

        raise AIServiceError(
            "AI returned invalid translation instruction."
        )

    return {
        "source_sentence": (
            source_sentence.strip()
        ),
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

    explanation = result.get(
        "explanation"
    )

    correction = result.get(
        "correction"
    )

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

    if not isinstance(
        explanation,
        str,
    ) or not explanation.strip():

        raise AIServiceError(
            "AI returned invalid explanation."
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
        "explanation": explanation.strip(),
        "correction": (
            correction.strip()
            if isinstance(correction, str)
            else None
        ),
    }

def _validate_example_result(
    result: dict,
) -> dict:

    example_answer = result.get(
        "example_answer"
    )

    explanation = result.get(
        "explanation"
    )

    if (
        not isinstance(
            example_answer,
            str,
        )
        or not example_answer.strip()
    ):
        raise AIServiceError(
            "AI returned invalid example answer."
        )

    if (
        not isinstance(
            explanation,
            str,
        )
        or not explanation.strip()
    ):
        raise AIServiceError(
            "AI returned invalid example explanation."
        )

    return {
        "example_answer": example_answer.strip(),
        "explanation": explanation.strip(),
    }


def generate_translation_challenge(
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
        prompts.translation_generation_prompt(
            target_word=target_word,
            translations=translations,
            native_language=native_language,
            learning_language=learning_language,
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
        "game_type": "translation",
        "flashcard_id": flashcard.id,
        "source_sentence": (
            result["source_sentence"]
        ),
        "instruction": result["instruction"],
    }


def evaluate_translation_challenge(
    *,
    user,
    flashcard_id: int,
    source_sentence: str,
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
        prompts.translation_evaluation_prompt(
            source_sentence=source_sentence,
            target_word=target_word,
            translations=translations,
            user_translation=answer,
            native_language=native_language,
            learning_language=learning_language,
        )
    )

    ai = DeepSeekService()

    result = ai.generate_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=500,
        temperature=0.2,
    )

    evaluation = _validate_evaluation_result(
        result
    )

    attempt = GameAttempt.objects.create(
        user=user,
        flashcard=flashcard,
        game_type="translation",
        is_correct=evaluation[
            "is_correct"
        ],
        user_answer=answer,
        score=evaluation[
            "score"
        ],
    )

    return attempt, evaluation

def give_up_translation_challenge(
    *,
    user,
    flashcard_id: int,
    source_sentence: str,
) -> tuple[GameAttempt, dict]:
    """
    Logs a failed attempt (no answer was submitted) and asks the AI
    for a single example translation, so the learner sees a correct
    usage instead of hitting a dead end.
    """
 
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
        prompts.translation_example_prompt(
            source_sentence=source_sentence,
            target_word=target_word,
            translations=translations,
            native_language=native_language,
            learning_language=learning_language,
        )
    )
 
    ai = DeepSeekService()
 
    result = ai.generate_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=300,
        temperature=0.4,
    )
 
    example = _validate_example_result(
        result
    )
 
    attempt = GameAttempt.objects.create(
        user=user,
        flashcard=flashcard,
        game_type="translation",
        is_correct=False,
        user_answer="",
        score=None,
        gave_up=True,
    )
 
    evaluation = {
        "is_correct": False,
        "score": 0.0,
        "feedback": (
            "You skipped this one — here's an "
            "example to learn from."
        ),
        "explanation": example["explanation"],
        "correction": (
            example["example_answer"]
        ),
    }
 
    return attempt, evaluation