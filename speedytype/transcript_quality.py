from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata


_SENTENCE_SPLIT = re.compile(r"[。！？!?；;\n]+")
_NUMBER = re.compile(r"(?:\d+(?:\.\d+)?)|(?:[零〇一二兩三四五六七八九十百千萬億]+)")
_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_UNITS = {"十": 10, "百": 100, "千": 1000, "萬": 10000, "億": 100000000}


def _chinese_number(value: str) -> str:
    if not any(char in _UNITS for char in value):
        return "".join(str(_DIGITS[char]) for char in value)
    total = 0
    section = 0
    number = 0
    for char in value:
        if char in _DIGITS:
            number = _DIGITS[char]
            continue
        unit = _UNITS[char]
        if unit < 10000:
            section += (number or 1) * unit
        else:
            section += number
            total += (section or 1) * unit
            section = 0
        number = 0
    return str(total + section + number)


def _canonical_number(value: str) -> str:
    if value[0].isdigit():
        return str(float(value)).rstrip("0").rstrip(".") if "." in value else str(int(value))
    return _chinese_number(value)


def normalize_transcript(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = _NUMBER.sub(lambda match: _canonical_number(match.group(0)), normalized)
    return "".join(char for char in normalized if char.isalnum())


def _sentences(text: str) -> list[str]:
    return [part.strip(" ，,\t\r") for part in _SENTENCE_SPLIT.split(text) if part.strip(" ，,\t\r")]


def _sentence_is_present(sentence: str, candidate_sentences: list[str]) -> bool:
    expected = normalize_transcript(sentence)
    if not expected:
        return True
    for candidate in candidate_sentences:
        actual = normalize_transcript(candidate)
        if expected in actual or actual in expected and len(actual) >= max(4, int(len(expected) * 0.85)):
            return True
        if SequenceMatcher(None, expected, actual, autojunk=False).ratio() >= 0.75:
            return True
    return False


@dataclass(frozen=True)
class TranscriptQuality:
    ordered_coverage: float
    missing_sentences: tuple[str, ...]
    new_duplicate_sentences: tuple[str, ...]
    reference_numbers: tuple[str, ...]
    candidate_numbers: tuple[str, ...]
    number_preserved: bool
    key_term_recall: float
    missing_key_terms: tuple[str, ...]

    @classmethod
    def compare(cls, reference: str, candidate: str, key_terms: list[str] | tuple[str, ...] = ()) -> "TranscriptQuality":
        reference_normalized = normalize_transcript(reference)
        candidate_normalized = normalize_transcript(candidate)
        matcher = SequenceMatcher(None, reference_normalized, candidate_normalized, autojunk=False)
        matched = sum(block.size for block in matcher.get_matching_blocks())
        ordered_coverage = matched / len(reference_normalized) if reference_normalized else 1.0

        reference_sentences = _sentences(reference)
        candidate_sentences = _sentences(candidate)
        missing_sentences = tuple(
            sentence for sentence in reference_sentences if not _sentence_is_present(sentence, candidate_sentences)
        )

        reference_counts = Counter(normalize_transcript(sentence) for sentence in reference_sentences)
        candidate_counts = Counter(normalize_transcript(sentence) for sentence in candidate_sentences)
        new_duplicates = tuple(
            sentence
            for sentence, count in candidate_counts.items()
            if sentence and count > max(1, reference_counts.get(sentence, 0))
        )

        reference_numbers = tuple(_canonical_number(value) for value in _NUMBER.findall(unicodedata.normalize("NFKC", reference)))
        candidate_numbers = tuple(_canonical_number(value) for value in _NUMBER.findall(unicodedata.normalize("NFKC", candidate)))
        number_preserved = Counter(reference_numbers) == Counter(candidate_numbers)

        relevant_terms = tuple(term for term in key_terms if normalize_transcript(term) in reference_normalized)
        missing_terms = tuple(term for term in relevant_terms if normalize_transcript(term) not in candidate_normalized)
        key_term_recall = (len(relevant_terms) - len(missing_terms)) / len(relevant_terms) if relevant_terms else 1.0
        return cls(
            ordered_coverage=ordered_coverage,
            missing_sentences=missing_sentences,
            new_duplicate_sentences=new_duplicates,
            reference_numbers=reference_numbers,
            candidate_numbers=candidate_numbers,
            number_preserved=number_preserved,
            key_term_recall=key_term_recall,
            missing_key_terms=missing_terms,
        )


def passes_quality_gate(metrics: TranscriptQuality) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    reasons.extend(f"missing complete sentence: {sentence}" for sentence in metrics.missing_sentences)
    reasons.extend(f"new duplicate sentence: {sentence}" for sentence in metrics.new_duplicate_sentences)
    if metrics.ordered_coverage < 0.98:
        reasons.append(f"ordered coverage {metrics.ordered_coverage:.3f} is below 0.980")
    if not metrics.number_preserved:
        reasons.append(
            f"numbers changed: reference={list(metrics.reference_numbers)} candidate={list(metrics.candidate_numbers)}"
        )
    if metrics.key_term_recall < 0.98:
        reasons.append(
            f"key-term recall {metrics.key_term_recall:.3f} is below 0.980; missing={list(metrics.missing_key_terms)}"
        )
    return not reasons, reasons


def passes_polished_regression_gate(metrics: TranscriptQuality) -> tuple[bool, list[str]]:
    """Gate for comparing two independently LLM-polished/restructured texts
    (e.g. hybrid-polished vs same-run batch-polished), as opposed to two raw
    STT transcripts of the same audio timeline.

    `passes_quality_gate`'s `ordered_coverage`/`missing_sentences` checks
    assume both texts preserve the same literal sentence-by-sentence order,
    which holds for STT transcripts of one audio file but not for two
    independent Gemini calls: Gemini is free to regroup a long narrative into
    differently-organized bullet sections each time, which is legitimate,
    faithful restructuring, not information loss. Verified against real data:
    the actual 295s-case batch vs. hybrid polished outputs (both good-quality,
    hand-inspected restructurings of the same content) score
    ordered_coverage=0.643 and trip ~13 "missing complete sentence" reasons
    purely from different bullet/section grouping, which would make this
    gate fail on every real hybrid run regardless of whether hybrid's
    chunking/merging actually lost anything - not a usable signal.

    What DOES stay meaningful across independent restructurings: whether the
    same key terms and numbers are still present somewhere in the output,
    since those are copied through verbatim by the polishing prompt rather
    than reworded. This gate checks only those two.
    """
    reasons: list[str] = []
    if not metrics.number_preserved:
        reasons.append(
            f"numbers changed: reference={list(metrics.reference_numbers)} candidate={list(metrics.candidate_numbers)}"
        )
    if metrics.key_term_recall < 0.98:
        reasons.append(
            f"key-term recall {metrics.key_term_recall:.3f} is below 0.980; missing={list(metrics.missing_key_terms)}"
        )
    return not reasons, reasons
