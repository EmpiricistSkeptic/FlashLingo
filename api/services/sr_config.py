"""
Tunable constants for the spaced-repetition engine.

All interval values are expressed in days (as floats) so the same unit
works uniformly whether the target gap is ten minutes (0.00694 days) or two
months (60 days). See the migration docstring for why `Flashcard.interval`
needs to be a FloatField rather than the original PositiveIntegerField.
"""

MINUTE = 1 / 1440
HOUR = 1 / 24

VALID_RESULTS = {"again", "hard", "good", "easy"}

# --- Learning phase ---------------------------------------------------------

# Flat interval used any time "Again" is pressed, whether the card is brand
# new, mid-learning, or a lapsed mature card. Kept short and constant so a
# forgotten card always resurfaces within minutes rather than compounding
# off wherever it happened to be.
AGAIN_INTERVAL_DAYS = 10 * MINUTE  # 10 minutes

# Ordered sequence of intervals a card moves through on successive "Good"
# presses before it graduates to the review phase. Two steps (short, then a
# full day) catch most short-term forgetting without turning the learning
# phase into a chore.
LEARNING_STEPS_DAYS = [
    1 * HOUR,  # 1st successful recall -> see it again in an hour
    1.0,       # 2nd successful recall -> see it again tomorrow
]

# Interval assigned when a card finishes all learning steps via "Good".
GRADUATING_INTERVAL_DAYS = 3.0

# Interval assigned when "Easy" graduates a card straight out of the
# learning phase (from new, or partway through the steps). Clearly more
# generous than the normal graduating interval.
EASY_GRADUATING_INTERVAL_DAYS = 4.0

# How much longer than the card's current learning step "Hard" schedules
# it for. 1.5x keeps it noticeably short of the next full step, and is
# capped at the graduating interval so a "hard" press can never accidentally
# schedule further out than a full graduation would.
HARD_STEP_MULTIPLIER = 1.5

# --- Ease factor -------------------------------------------------------------

DEFAULT_EASE_FACTOR = 2.5

# Below ~1.3 the ease factor stops meaningfully protecting a card from
# showing up too often; this is the same floor SM-2 popularised and it
# still holds up in practice.
MIN_EASE_FACTOR = 1.3

# Above ~3.5 further increases produce jumps that feel arbitrary, and risk
# a card vanishing from rotation for a year+ even though light periodic
# exposure still has value in a language app.
MAX_EASE_FACTOR = 3.5

EASE_DELTA_AGAIN = -0.20
EASE_DELTA_HARD = -0.15
EASE_DELTA_GOOD = 0.0
EASE_DELTA_EASY = 0.15

# --- Review (mature) phase ----------------------------------------------------

# "Hard" on a mature card should still grow the interval (it was a real,
# if effortful, recall) but far more conservatively than ease-factor-driven
# growth, which is often 2x+.
HARD_INTERVAL_MULTIPLIER = 1.2

# Extra multiplier stacked on top of normal ease-factor growth for "Easy",
# so it is unambiguously the most rewarding option.
EASY_BONUS_MULTIPLIER = 1.3

# Once a card graduates, never schedule sub-day reviews again - even a very
# hard mature card waits at least a day.
MIN_REVIEW_INTERVAL_DAYS = 1

# Absolute ceiling so an extremely easy card doesn't drift out to
# multi-year intervals and effectively disappear from the deck.
MAX_INTERVAL_DAYS = 365