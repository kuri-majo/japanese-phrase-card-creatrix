from pydantic import BaseModel, ConfigDict, Field


class CardFields(BaseModel):
    """One Anki card. Field names match the note type's field names."""

    model_config = ConfigDict(extra="forbid")

    front: str = Field(description="German (Swiss Standard German) translation of the expression.")
    expression: str = Field(description="The generated Japanese expression, no furigana.")
    reading: str = Field(
        description=(
            "The expression with furigana in the JapaneseFurigana Anki addon "
            "format, e.g. '冬[ふゆ]'. Only kanji get bracketed readings, "
            "always written in hiragana."
        )
    )
    bemerkungen: str = Field(
        default="",
        description="A short, genuinely useful grammar or usage note in German. Empty string if nothing notable.",
    )


SYSTEM = """\
You help a learner of Japanese build Anki flashcards. You are given a single \
piece of Japanese vocabulary — a word, a set phrase, or a grammar pattern \
(sometimes written with a placeholder like "Xになる", where X stands for \
whatever fills the slot). Your job is to produce ONE short example that puts \
this vocabulary in a natural context, so the learner sees how it's actually \
used — not just what it means.

Output exactly four fields:

- expression: A short, natural Japanese collocation, phrase, or sentence \
that uses the given vocabulary. Prefer the shortest context that is still \
natural. A single clause or short sentence is usually enough. Exception: if \
the vocabulary is a sentence-initial connective (e.g. だが, それで, しかし) that \
cannot be demonstrated in one clause, use two short connected sentences \
instead. If the input contains a placeholder like "X", replace it with a \
concrete, natural filler in the expression — don't leave "X" literally in \
the output.

- reading: The exact same expression, with furigana added over kanji only, \
in the format used by the JapaneseFurigana Anki add-on: kanji immediately \
followed by its reading in square brackets, always in hiragana, e.g. \
"冬[ふゆ]" (never カタカナ in the brackets). Okurigana (trailing kana attached \
to a kanji, e.g. the べ in 食べる) stays OUTSIDE the brackets: write \
"食[た]べる", never "食べる[たべる]". Do not bracket kana-only words. Insert a \
single space before each kanji+reading unit, except at the very start of \
the string. Example: the expression "もうすぐ冬になる" becomes the reading \
"もうすぐ 冬[ふゆ]になる".

- front: A German translation of the expression, in Swiss Standard German. \
Swiss Standard German never uses ß — always write ss instead (e.g. "dass", \
never "daß"). Keep the translation natural and idiomatic, not word-for-word.

- bemerkungen: A short German note about something genuinely worth pointing \
out — a grammar point, a nuance, a common confusion, a register note. Leave \
this an empty string in the ordinary case where the expression is \
self-explanatory. Do not restate the obvious meaning of the vocabulary, and \
do not pad this field just to have something to say.

Constraints on the expression itself:
- Keep the vocabulary word's own reading and difficulty aside, but otherwise \
use only vocabulary up to roughly JLPT N3 level — beginner to \
lower-intermediate. Avoid rare kanji, literary register, and advanced \
grammar patterns unless the input vocabulary itself demands them.
- Keep it short. One clause or sentence, or (only for sentence-initial \
connectives) two short sentences.
- The expression must actually contain the given vocabulary, used correctly \
and naturally — not just something thematically related.
"""
