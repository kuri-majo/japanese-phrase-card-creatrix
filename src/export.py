"""Builds the Anki-importable TSV file from the accumulated deck."""

_COLUMNS = ("front", "expression", "reading", "bemerkungen")
_HEADER_ROW = "#columns:Front\tExpression\tReading\tBemerkungen"


def _clean_field(value: str) -> str:
    """Anki's tab-separated import format uses tabs as the sole field
    delimiter and newlines as the sole record delimiter, so both must be
    stripped from field values -- a stray tab would silently shift every
    later field in that row, and a stray newline would split one card
    into two "notes"."""
    return value.replace("\t", " ").replace("\n", " ").replace("\r", " ").strip()


def build_tsv(cards: list[dict], notetype: str = "", deck: str = "") -> str:
    """cards: dicts with front/expression/reading/bemerkungen keys, in the
    order they should appear in the deck. notetype/deck are optional --
    when blank, the corresponding Anki import header line is omitted so
    Anki falls back to whatever's selected in the import dialog."""
    lines = ["#separator:tab", "#html:false"]
    if notetype := notetype.strip():
        lines.append(f"#notetype:{_clean_field(notetype)}")
    if deck := deck.strip():
        lines.append(f"#deck:{_clean_field(deck)}")
    lines.append(_HEADER_ROW)

    for card in cards:
        row = "\t".join(_clean_field(str(card.get(field, ""))) for field in _COLUMNS)
        lines.append(row)

    return "\n".join(lines) + "\n"
