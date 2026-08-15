from export import build_tsv


def test_includes_standard_header_lines():
    lines = build_tsv([]).splitlines()
    assert lines[0] == "#separator:tab"
    assert lines[1] == "#html:false"


def test_omits_notetype_and_deck_lines_when_blank():
    tsv = build_tsv([])
    assert "#notetype:" not in tsv
    assert "#deck:" not in tsv


def test_includes_notetype_and_deck_lines_when_given():
    tsv = build_tsv([], notetype="Japanese", deck="Vocab")
    assert "#notetype:Japanese" in tsv
    assert "#deck:Vocab" in tsv


def test_columns_header_matches_anki_field_names():
    assert "#columns:Front\tExpression\tReading\tBemerkungen" in build_tsv([])


def test_one_row_per_card_tab_separated_in_field_order():
    cards = [
        {"front": "a", "expression": "b", "reading": "c", "bemerkungen": "d"},
        {"front": "e", "expression": "f", "reading": "g", "bemerkungen": ""},
    ]
    lines = build_tsv(cards).splitlines()
    assert lines[-2] == "a\tb\tc\td"
    assert lines[-1] == "e\tf\tg\t"


def test_strips_tabs_and_newlines_from_field_values():
    # A stray tab would silently shift every later column in the row; a
    # stray newline would split one card into two Anki "notes". Both must
    # be scrubbed, not just passed through.
    cards = [{"front": "a\tb", "expression": "c\nd", "reading": "e\r\nf", "bemerkungen": ""}]
    data_line = build_tsv(cards).splitlines()[-1]
    assert data_line == "a b\tc d\te  f\t"


def test_missing_field_on_a_card_becomes_an_empty_column_not_an_error():
    tsv = build_tsv([{"front": "only this"}])
    assert tsv.splitlines()[-1] == "only this\t\t\t"
