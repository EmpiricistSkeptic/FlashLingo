"""
Spaced repetition scheduling engine for language-learning flashcards.

This is a custom two-phase algorithm, not a copy of SM-2, Anki, or FSRS:

1. Learning phase (status "new" / "learning"): a short, fixed sequence of
   sub-day "learning steps" gets a freshly created or recently-failed card
   back in front of the user quickly, the way most modern flashcard apps
   handle onboarding a card. next_review is scheduled to the minute here.

2. Review phase (status "learned"): once a card survives the learning
   steps, scheduling switches to exponential day-based growth driven by the
   per-card `ease_factor`, in the spirit of SM-2 but simplified for four
   review buttons instead of a 0-5 grade scale.

Public entrypoint: `review_flashcard(flashcard, result)`.
"""
from datetime import timedelta

from django.utils import timezone

from . import sr_config as cfg


def review_flashcard(flashcard, result):
    """
    Apply a single review result ("again" | "hard" | "good" | "easy") to a
    Flashcard instance, updating its scheduling state in place and saving
    it. Returns the same instance for convenience.
    """
    if result not in cfg.VALID_RESULTS:
        raise ValueError(
            f"Invalid review result {result!r}; expected one of {sorted(cfg.VALID_RESULTS)}"
        )

    now = timezone.now()
    flashcard.review_count += 1

    if flashcard.status in ("new", "learning"):
        _apply_learning_review(flashcard, result, now)
    else:  # "learned"
        _apply_mature_review(flashcard, result, now)

    flashcard.save()
    return flashcard


# ---------------------------------------------------------------------------
# Learning phase: "new" -> "learning" -> "learned"
# ---------------------------------------------------------------------------

def _apply_learning_review(flashcard, result, now):
    if result == "again":
        flashcard.ease_factor = _adjust_ease(flashcard.ease_factor, cfg.EASE_DELTA_AGAIN)
        flashcard.repetitions = 0
        flashcard.status = "learning"
        flashcard.learning_step = 0
        flashcard.interval = cfg.AGAIN_INTERVAL_DAYS

    elif result == "easy":
        flashcard.ease_factor = _adjust_ease(flashcard.ease_factor, cfg.EASE_DELTA_EASY)
        flashcard.repetitions += 1
        flashcard.status = "learned"
        flashcard.learning_step = 0
        flashcard.interval = cfg.EASY_GRADUATING_INTERVAL_DAYS

    elif result == "hard":
        # learning_step counts *completed* steps, so the step Hard should
        # re-schedule (without advancing) is learning_step - 1; 0 means no
        # step has been completed yet, so fall back to the "Again" baseline.
        step_duration = (
            cfg.LEARNING_STEPS_DAYS[flashcard.learning_step - 1]
            if flashcard.learning_step > 0
            else cfg.AGAIN_INTERVAL_DAYS
        )
        flashcard.ease_factor = _adjust_ease(flashcard.ease_factor, cfg.EASE_DELTA_HARD)
        flashcard.repetitions += 1
        flashcard.status = "learning"
        flashcard.interval = min(
            step_duration * cfg.HARD_STEP_MULTIPLIER, cfg.GRADUATING_INTERVAL_DAYS
        )
        # learning_step is intentionally left unchanged: Hard re-shows the
        # same step, it doesn't advance to the next one.

    elif result == "good":
        flashcard.ease_factor = _adjust_ease(flashcard.ease_factor, cfg.EASE_DELTA_GOOD)
        flashcard.repetitions += 1
        if flashcard.learning_step < len(cfg.LEARNING_STEPS_DAYS):
            flashcard.status = "learning"
            flashcard.interval = cfg.LEARNING_STEPS_DAYS[flashcard.learning_step]
            flashcard.learning_step += 1
        else:
            flashcard.status = "learned"
            flashcard.learning_step = 0
            flashcard.interval = cfg.GRADUATING_INTERVAL_DAYS

    flashcard.next_review = now + timedelta(days=flashcard.interval)


# ---------------------------------------------------------------------------
# Review phase: "learned"
# ---------------------------------------------------------------------------

def _apply_mature_review(flashcard, result, now):
    if result == "again":
        # Lapse: a mature card that was forgotten drops back into the
        # learning phase rather than just shrinking its interval.
        flashcard.ease_factor = _adjust_ease(flashcard.ease_factor, cfg.EASE_DELTA_AGAIN)
        flashcard.repetitions = 0
        flashcard.status = "learning"
        flashcard.learning_step = 0
        flashcard.interval = cfg.AGAIN_INTERVAL_DAYS

    elif result == "hard":
        flashcard.ease_factor = _adjust_ease(flashcard.ease_factor, cfg.EASE_DELTA_HARD)
        flashcard.repetitions += 1
        grown = max(
            flashcard.interval * cfg.HARD_INTERVAL_MULTIPLIER,
            flashcard.interval + 1,
        )
        flashcard.interval = _cap_mature_interval(grown)
        flashcard.status = "learned"

    elif result == "good":
        flashcard.ease_factor = _adjust_ease(flashcard.ease_factor, cfg.EASE_DELTA_GOOD)
        flashcard.repetitions += 1
        grown = flashcard.interval * flashcard.ease_factor
        flashcard.interval = _cap_mature_interval(grown)
        flashcard.status = "learned"

    elif result == "easy":
        flashcard.ease_factor = _adjust_ease(flashcard.ease_factor, cfg.EASE_DELTA_EASY)
        flashcard.repetitions += 1
        grown = flashcard.interval * flashcard.ease_factor * cfg.EASY_BONUS_MULTIPLIER
        flashcard.interval = _cap_mature_interval(grown)
        flashcard.status = "learned"

    flashcard.next_review = now + timedelta(days=flashcard.interval)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _adjust_ease(current_ease, delta):
    return round(min(cfg.MAX_EASE_FACTOR, max(cfg.MIN_EASE_FACTOR, current_ease + delta)), 4)


def _cap_mature_interval(value_days):
    bounded = max(cfg.MIN_REVIEW_INTERVAL_DAYS, min(cfg.MAX_INTERVAL_DAYS, value_days))
    return float(round(bounded))
