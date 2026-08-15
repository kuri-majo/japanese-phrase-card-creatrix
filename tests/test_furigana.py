from furigana import _plain_reading, readings_agree, to_furigana


class TestToFurigana:
    def test_plan_worked_example(self):
        # The exact example from the app's spec: verb + kanji with a
        # single-kanji token, one bracket, one leading space before it.
        assert to_furigana("もうすぐ冬になる") == "もうすぐ 冬[ふゆ]になる"

    def test_okurigana_stays_outside_the_brackets(self):
        # 食べる: べる is okurigana already present as kana in the surface
        # form and must not be re-included inside the brackets.
        assert to_furigana("食べる") == "食[た]べる"

    def test_kana_only_sentence_is_left_unchanged(self):
        assert to_furigana("これはペンです") == "これはペンです"

    def test_multiple_bracketed_units_each_get_a_leading_space(self):
        assert to_furigana("明日は雨だ") == "明日[あす]は 雨[あめ]だ"

    def test_bracket_at_the_very_start_gets_no_leading_space(self):
        result = to_furigana("冬になる")
        assert result == "冬[ふゆ]になる"
        assert not result.startswith(" ")

    def test_compound_kanji_with_interior_kana_brackets_as_one_unit(self):
        # 書き込む: 書 and 込 are both kanji with き between them and no
        # space in the dictionary reading between them; the whole kanji+
        # interior-kana span is bracketed together rather than split.
        assert to_furigana("書き込む") == "書き込[かきこ]む"


class TestReadingsAgree:
    def test_identical_reading_agrees(self):
        example = to_furigana("もうすぐ冬になる")
        assert readings_agree(example, example) is True

    def test_same_pronunciation_different_but_valid_spacing_agrees(self):
        # A single bracketed unit with no other bracket/word before it in
        # its clause never has swallow risk, so this is a legitimate
        # same-reading-different-formatting case.
        assert readings_agree("冬[ふゆ]になる", "冬[ふゆ]になる") is True

    def test_genuinely_different_reading_disagrees(self):
        # 明日 read as あした vs the dictionary's あす — the real
        # ambiguous-kanji scenario the disagreement flag exists for.
        fugashi_reading = to_furigana("明日は雨だ")
        llm_reading = "明日[あした]は 雨[あめ]だ"
        assert readings_agree(fugashi_reading, llm_reading) is False

    def test_missing_required_space_before_a_bracket_still_agrees(self):
        # Regression test: an earlier version of _plain_reading's regex
        # greedily matched any run of non-bracket, non-space characters
        # immediately before "[", so when a required leading space was
        # missing (e.g. "...は雨[あめ]..."), it silently swallowed "は"
        # into the match and discarded it — corrupting the comparison
        # rather than just being a formatting nit. Since the underlying
        # pronunciation is genuinely identical, the fixed version agrees
        # here (it isolates each bracket's own kanji-anchored prefix and
        # preserves leaked-in text like "は" instead of dropping it).
        fugashi_reading = to_furigana("明日は雨だ")  # "明日[あす]は 雨[あめ]だ"
        llm_reading_missing_space = "明日[あす]は雨[あめ]だ"
        assert readings_agree(fugashi_reading, llm_reading_missing_space) is True

    def test_missing_space_does_not_drop_characters(self):
        # Same scenario as above, verified at the _plain_reading level:
        # "は" must survive extraction, not vanish.
        result = _plain_reading("明日[あす]は雨[あめ]だ")
        assert "は" in result
        assert result == "あすはあめだ"

    def test_compound_kanji_with_interior_kana_still_agrees_with_itself(self):
        # Guards the fix above from overcorrecting: 書き込[かきこ] has
        # interior kana (き) as a legitimate part of ONE bracket's own
        # unit (not leaked-in text from a previous word), because it
        # starts right at the first kanji character with no preceding
        # unmatched text. _strip_one_bracket's kanji-anchored scan must
        # keep it as a single unit rather than truncating to just the
        # last kanji character.
        example = to_furigana("書き込む")  # "書き込[かきこ]む"
        assert readings_agree(example, example) is True
