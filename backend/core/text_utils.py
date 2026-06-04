"""Text helpers for SEO.

`transliterate_slug` mirrors the frontend `slugify` (frontend/src/utils/slugify.js)
so that slugs generated on the backend match the URLs produced in the UI.
"""

import re

# Cyrillic (ru/uk) -> Latin, identical mapping to the frontend slugify.
_CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "і": "i", "ї": "yi", "є": "ye",
}


def transliterate_slug(text: str) -> str:
    """Convert an arbitrary (ru/uk) title into a clean ASCII slug.

    Matches frontend slugify(): lowercase, transliterate Cyrillic, drop other
    non-[a-z0-9], collapse whitespace/hyphens to a single hyphen.
    """
    if not isinstance(text, str):
        return ""

    slug = text.lower()
    slug = "".join(_CYRILLIC_TO_LATIN.get(ch, ch) for ch in slug)
    # Replace anything that's not a-z, 0-9, space or hyphen with a space.
    slug = re.sub(r"[^a-z0-9\s-]", " ", slug)
    # Collapse whitespace / repeated hyphens into a single hyphen.
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug
