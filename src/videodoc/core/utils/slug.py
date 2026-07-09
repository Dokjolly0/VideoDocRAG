import re
import unicodedata


def slugify(name: str) -> str:
    """Turn a human-readable project name into its canonical, machine-safe slug.

    The slug is VideoDocRAG's one identifier for a project: it is the key
    used in the local project registry (``ProjectRegistry``), the default
    ``project.slug`` written to ``config.yaml``, and the folder name used
    under the default projects home when ``videodoc init`` is called
    without ``--path``. ``ProjectService.init`` and ``ProjectService.link``
    both key the registry on this same slug precisely so that the same
    project is always reachable under the same identifier, no matter how
    it was created (see docs/features/slugify.md).

    Algorithm, in order:
    1. Unicode-normalize (NFKD) and drop anything that can't be
       transliterated to plain ASCII, so accented/non-Latin characters are
       folded to their closest ASCII equivalent instead of being kept as
       opaque bytes (e.g. "città" -> "citta").
    2. Lowercase everything.
    3. Collapse every run of characters that isn't ``[a-z0-9]`` into a
       single hyphen, then trim leading/trailing hyphens.

    Examples:
        >>> slugify("Corso Software X")
        'corso-software-x'
        >>> slugify("Città è già pronta!!")
        'citta-e-gia-pronta'

    Raises:
        ValueError: if the input contains no ASCII alphanumeric character
        at all (e.g. ``slugify("!!!")`` or ``slugify("こんにちは")``), so
        the result would otherwise be an empty, useless slug. Callers in
        ``core`` translate this into the domain exception
        ``InvalidProjectNameError`` at the boundary where a project name
        is first accepted from a user (``ProjectService.init``) — this
        function itself stays a small, dependency-free utility and never
        raises a VideoDocRAG-specific exception type.
    """
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if not slug:
        raise ValueError(f"Cannot derive a valid slug from project name: {name!r}")
    return slug
