"""
Algorithm 4 — Code Similarity Detection
===========================================
Flags pairs of student submissions for the same assignment that look
suspiciously alike, so a teacher can review them — not an automatic
accusation, just a ranked worklist.

Approach
---------
1. Normalize each submission's source: strip comments and blank lines,
   collapse whitespace, then tokenize into an identifier/operator/
   keyword stream. This makes the comparison robust to cosmetic
   differences (renamed variables, reformatted whitespace, different
   comments) while still being sensitive to structural copying —
   exactly the kind of superficial disguise students actually use.
2. Compare every pair of (most-recent-per-student) submissions for the
   assignment using difflib.SequenceMatcher's ratio() over the token
   streams — a well-established, dependency-free similarity measure
   (no need for a heavier AST-diffing library for this scope).
3. Rank pairs by similarity; anything above SIMILARITY_THRESHOLD is
   surfaced to the teacher, highest first.

This is intentionally a *detection aid*, not a verdict — two students
solving a genuinely simple problem (e.g. "print the sum of two
numbers") will legitimately produce near-identical short solutions, so
similarity alone is a signal to look at, not proof of copying.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from assignments.models import Assignment, Submission

SIMILARITY_THRESHOLD = 0.75

# Matches # and // line comments, and /* */ and """ ''' block comments —
# covers Python, C, and Java, the three languages this project supports.
_COMMENT_PATTERNS = [
    re.compile(r"#.*"),
    re.compile(r"//.*"),
    re.compile(r"/\*.*?\*/", re.DOTALL),
    re.compile(r'""".*?"""', re.DOTALL),
    re.compile(r"'''.*?'''", re.DOTALL),
]
_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[^\sA-Za-z0-9_]")


def tokenize(source: str) -> list[str]:
    """Strips comments, then splits into a stream of identifiers/keywords
    and individual punctuation/operator characters."""
    cleaned = source
    for pattern in _COMMENT_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return _TOKEN_PATTERN.findall(cleaned)


def similarity(source_a: str, source_b: str) -> float:
    """Returns a 0.0-1.0 similarity ratio between two source strings."""
    tokens_a = tokenize(source_a)
    tokens_b = tokenize(source_b)
    if not tokens_a or not tokens_b:
        return 0.0
    return difflib.SequenceMatcher(None, tokens_a, tokens_b).ratio()


@dataclass
class SimilarPair:
    submission_a: Submission
    submission_b: Submission
    score: float


def find_similar_pairs(assignment: Assignment, threshold: float = SIMILARITY_THRESHOLD) -> list[SimilarPair]:
    """
    Compares the most recent submission per student for this assignment
    against every other student's most recent submission, and returns
    pairs at or above `threshold`, sorted by similarity descending.
    """
    latest_by_student = {}
    for submission in (
        Submission.objects.filter(assignment=assignment)
        .select_related("student__user")
        .order_by("student_id", "-attempt_number")
    ):
        if submission.student_id not in latest_by_student:
            latest_by_student[submission.student_id] = submission

    submissions = list(latest_by_student.values())
    pairs = []
    for i in range(len(submissions)):
        for j in range(i + 1, len(submissions)):
            score = similarity(submissions[i].source_code, submissions[j].source_code)
            if score >= threshold:
                pairs.append(SimilarPair(submissions[i], submissions[j], round(score, 3)))

    pairs.sort(key=lambda p: p.score, reverse=True)
    return pairs
