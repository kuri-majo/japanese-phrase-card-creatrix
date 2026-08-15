import re

import fugashi

_tagger = fugashi.Tagger()

_KATAKANA_TO_HIRAGANA = str.maketrans({chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)})


def _to_hiragana(katakana: str) -> str:
    return katakana.translate(_KATAKANA_TO_HIRAGANA)


def _is_kanji(ch: str) -> bool:
    return "一" <= ch <= "鿿" or ch == "々"  # CJK ideographs + 々 iteration mark


def _has_kanji(s: str) -> bool:
    return any(_is_kanji(ch) for ch in s)


def _token_reading(surface: str, reading_katakana: str | None) -> str:
    """Hiragana reading for one token. Falls back to the surface itself for
    tokens fugashi has no dictionary reading for (numbers, punctuation,
    unknown words) — such tokens are left unbracketed by _bracket_token."""
    if not reading_katakana:
        return surface
    return _to_hiragana(reading_katakana)


def _bracket_token(surface: str, reading_hira: str) -> str:
    """Wrap the kanji portion of one token in furigana brackets, per the
    JapaneseFurigana add-on format: kanji immediately followed by
    [reading]. Okurigana already present in the surface (leading or
    trailing kana) is peeled off by matching it against the same
    characters in the reading, and stays outside the brackets — e.g.
    surface "食べる" + reading "たべる" -> "食[た]べる"."""
    if not _has_kanji(surface) or surface == reading_hira:
        return surface

    lead = 0
    while (
        lead < len(surface)
        and lead < len(reading_hira)
        and surface[lead] == reading_hira[lead]
        and not _is_kanji(surface[lead])
    ):
        lead += 1

    trail = 0
    while (
        trail < len(surface) - lead
        and trail < len(reading_hira) - lead
        and surface[-1 - trail] == reading_hira[-1 - trail]
        and not _is_kanji(surface[-1 - trail])
    ):
        trail += 1

    mid_surface = surface[lead : len(surface) - trail] if trail else surface[lead:]
    mid_reading = reading_hira[lead : len(reading_hira) - trail] if trail else reading_hira[lead:]

    if not mid_surface:
        return surface

    lead_str = surface[:lead]
    trail_str = surface[len(surface) - trail :] if trail else ""
    return f"{lead_str}{mid_surface}[{mid_reading}]{trail_str}"


def to_furigana(expression: str) -> str:
    """Deterministic Reading field: `expression` with furigana added over
    kanji, JapaneseFurigana add-on format ('冬[ふゆ]'), with a leading space
    before every bracketed unit except at the very start of the string."""
    pieces: list[str] = []
    for word in _tagger(expression):
        reading_hira = _token_reading(word.surface, word.feature.kana)
        piece = _bracket_token(word.surface, reading_hira)
        if "[" in piece and pieces:
            pieces.append(" " + piece)
        else:
            pieces.append(piece)
    return "".join(pieces)


_READING_RUN = re.compile(r"(?:^|(?<=[\s\]]))([^\[\]\s]+)\[([^\]]+)\]")


def _strip_one_bracket(match: re.Match[str]) -> str:
    """Replace one "<prefix>[<reading>]" run with just its reading — but
    only the part of the prefix that actually belongs to this bracket. A
    legitimate bracket's prefix always starts at its first kanji
    character (mirroring _bracket_token's `lead` computation); anything
    before that within the matched prefix is text that leaked in because
    a required separating space was missing (see
    test_missing_space_does_not_drop_characters) and must be preserved
    as-is rather than discarded."""
    prefix, reading = match.group(1), match.group(2)
    start = next((i for i, ch in enumerate(prefix) if _is_kanji(ch)), 0)
    return prefix[:start] + reading


def _plain_reading(annotated: str) -> str:
    """Collapse a furigana-annotated string down to its bare hiragana
    pronunciation, so two differently-formatted (but phonetically
    identical) readings can be compared."""
    stripped = _READING_RUN.sub(_strip_one_bracket, annotated)
    return re.sub(r"\s+", "", stripped)


def readings_agree(fugashi_reading: str, llm_reading: str) -> bool:
    """Whether the LLM's own `reading` field and the deterministic fugashi
    reading describe the same pronunciation, ignoring spacing/formatting
    differences between the two."""
    return _plain_reading(fugashi_reading) == _plain_reading(llm_reading)
