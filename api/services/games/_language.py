from rest_framework.exceptions import ValidationError


def get_language_pair_for(flashcard):
    """
    Current schema assumption:

    Flashcard
        ↓
    categories (ManyToMany)
        ↓
    Category.language_pair
    """

    category = (
        flashcard.categories
        .select_related("language_pair")
        .first()
    )

    if category is None:
        raise ValidationError(
            "Flashcard has no category."
        )

    language_pair = getattr(
        category,
        "language_pair",
        None,
    )

    if language_pair is None:
        raise ValidationError(
            "Flashcard has no language pair."
        )

    return language_pair


def language_names(language_pair):
    """
    Returns display names used in AI prompts.
    """

    learning_language = (
        language_pair.learning_language
    )

    native_language = (
        language_pair.native_language
    )

    return (
        learning_language,
        native_language,
    )