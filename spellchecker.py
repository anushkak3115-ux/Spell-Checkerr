#!/usr/bin/env python3
"""
spellchecker.py - A command-line spell checker.

Combines two classic techniques:
  * A hand-built hash table (separate chaining) for O(1) average-time
    dictionary lookups.
  * Levenshtein edit distance to rank correction suggestions.

Usage:
    python spellchecker.py -d words.txt essay.txt
    echo "helo wrld" | python spellchecker.py -d words.txt
    python spellchecker.py -d words.txt -n 3 file1.txt file2.txt

Dictionary: one word per line. If -d is omitted, /usr/share/dict/words is used.
"""

import argparse
import heapq
import re
import sys
from typing import Iterable, Iterator, List, Optional, Tuple

DEFAULT_DICTIONARY = "/usr/share/dict/words"
WORD_PATTERN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*")  # letters, inner apostrophes


# --------------------------------------------------------------------------- #
# Hash table with separate chaining
# --------------------------------------------------------------------------- #
class _Node:
    """A single link in a bucket's chain."""

    __slots__ = ("key", "next")

    def __init__(self, key: str, next_node: Optional["_Node"] = None):
        self.key = key
        self.next = next_node


class HashTable:
    """
    A set of strings backed by an array of linked-list buckets.

    * Hash function: 32-bit FNV-1a (fast, good avalanche behaviour on text).
    * Collisions: separate chaining (each bucket is a singly linked list).
    * Resizing: table doubles when load factor exceeds 0.75, keeping
      chains short so lookups stay O(1) on average.
    """

    MAX_LOAD_FACTOR = 0.75

    def __init__(self, capacity: int = 1024):
        self._buckets: List[Optional[_Node]] = [None] * capacity
        self._size = 0

    # -- hashing ----------------------------------------------------------- #
    @staticmethod
    def _hash(key: str) -> int:
        h = 0x811C9DC5  # FNV offset basis
        for byte in key.encode("utf-8"):
            h ^= byte
            h = (h * 0x01000193) & 0xFFFFFFFF  # FNV prime, keep 32 bits
        return h

    def _index(self, key: str) -> int:
        return self._hash(key) % len(self._buckets)

    # -- public API -------------------------------------------------------- #
    def add(self, key: str) -> bool:
        """Insert key. Returns True if it was new, False if already present."""
        if key in self:
            return False
        if (self._size + 1) / len(self._buckets) > self.MAX_LOAD_FACTOR:
            self._resize(len(self._buckets) * 2)
        idx = self._index(key)
        self._buckets[idx] = _Node(key, self._buckets[idx])  # push at chain head
        self._size += 1
        return True

    def __contains__(self, key: str) -> bool:
        node = self._buckets[self._index(key)]
        while node:
            if node.key == key:
                return True
            node = node.next
        return False

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[str]:
        for node in self._buckets:
            while node:
                yield node.key
                node = node.next

    # -- internals --------------------------------------------------------- #
    def _resize(self, new_capacity: int) -> None:
        old = self._buckets
        self._buckets = [None] * new_capacity
        for node in old:
            while node:
                nxt = node.next
                idx = self._index(node.key)
                node.next = self._buckets[idx]  # relink existing node, no realloc
                self._buckets[idx] = node
                node = nxt

    def stats(self) -> Tuple[int, int, float, int]:
        """Return (buckets, entries, load factor, longest chain) for diagnostics."""
        longest = 0
        for node in self._buckets:
            length = 0
            while node:
                length += 1
                node = node.next
            longest = max(longest, length)
        return len(self._buckets), self._size, self._size / len(self._buckets), longest


# --------------------------------------------------------------------------- #
# Levenshtein distance
# --------------------------------------------------------------------------- #
def levenshtein(a: str, b: str, max_dist: Optional[int] = None) -> int:
    """
    Minimum number of single-character insertions, deletions or substitutions
    needed to turn `a` into `b`.

    Uses dynamic programming with two rolling rows: O(len(a)*len(b)) time,
    O(min(len(a), len(b))) space.

    If `max_dist` is given, returns max_dist + 1 as soon as the distance is
    guaranteed to exceed it (early exit used to speed up suggestion search).
    """
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a  # make b the shorter string -> smaller rows
    if max_dist is not None and len(a) - len(b) > max_dist:
        return max_dist + 1
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1,          # deletion
                            curr[j - 1] + 1,      # insertion
                            prev[j - 1] + cost))  # substitution / match
        if max_dist is not None and min(curr) > max_dist:
            return max_dist + 1  # every path already too costly
        prev = curr
    return prev[-1]


def damerau_levenshtein(a: str, b: str, max_dist: Optional[int] = None) -> int:
    """
    Levenshtein distance extended with adjacent transpositions
    (optimal string alignment variant): swapping two neighbouring letters,
    e.g. 'ab' -> 'ba', costs 1 edit instead of 2.

    Keeps three rows (current, previous, and the one before) because a
    transposition looks back two rows. Same O(len(a)*len(b)) time.
    """
    if a == b:
        return 0
    if max_dist is not None and abs(len(a) - len(b)) > max_dist:
        return max_dist + 1
    if not a:
        return len(b)
    if not b:
        return len(a)

    prev2: List[int] = []
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        curr = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(prev[j] + 1,          # deletion
                          curr[j - 1] + 1,      # insertion
                          prev[j - 1] + cost)   # substitution / match
            if (i > 1 and j > 1 and a[i - 1] == b[j - 2]
                    and a[i - 2] == b[j - 1]):
                curr[j] = min(curr[j], prev2[j - 2] + 1)  # transposition
        if max_dist is not None and min(curr) > max_dist and min(prev) > max_dist:
            return max_dist + 1
        prev2, prev = prev, curr
    return prev[-1]


# --------------------------------------------------------------------------- #
# Spell checker
# --------------------------------------------------------------------------- #
class SpellChecker:
    def __init__(self, words: Iterable[str], metric=levenshtein):
        self.metric = metric  # distance function used to rank suggestions
        self.table = HashTable()
        for w in words:
            w = w.strip().lower()
            if w:
                self.table.add(w)

    @classmethod
    def from_file(cls, path: str, metric=levenshtein) -> "SpellChecker":
        with open(path, encoding="utf-8", errors="ignore") as fh:
            return cls(fh, metric)

    def is_correct(self, word: str) -> bool:
        return word.lower() in self.table

    def suggest(self, word: str, n: int = 5) -> List[Tuple[str, int]]:
        """
        Return up to n (word, distance) pairs, closest first; ties are broken
        alphabetically so output is deterministic.
        """
        word = word.lower()
        # Max-heap of the n best so far: (-distance, reverse-alpha key, word), so the
        # heap root is always the *worst* kept candidate.
        best: List[Tuple[int, Tuple[int, ...], str]] = []
        for candidate in self.table:
            # Tightest distance still worth finding once we hold n candidates.
            limit = -best[0][0] if len(best) == n else None
            d = self.metric(word, candidate, limit)
            if limit is not None and d > limit:
                continue
            item = (-d, _negate(candidate), candidate)
            if len(best) < n:
                heapq.heappush(best, item)
            elif item[:2] > best[0][:2]:
                heapq.heapreplace(best, item)
        return sorted(((w, -d) for d, _, w in best), key=lambda p: (p[1], p[0]))


def _negate(s: str) -> Tuple[int, ...]:
    """Make a string sort in reverse so a max-heap can break ties alphabetically."""
    return tuple(-ord(c) for c in s)


# --------------------------------------------------------------------------- #
# Text processing & CLI
# --------------------------------------------------------------------------- #
def tokenize(line: str) -> List[str]:
    """Extract words, dropping punctuation/digits; case is normalised later."""
    return WORD_PATTERN.findall(line)


def check_stream(checker: SpellChecker, stream, name: str, n: int) -> int:
    """Check every word in `stream`; print suggestions. Returns # of misspellings."""
    errors = 0
    seen = {}  # cache suggestions so repeated typos are computed once
    for lineno, line in enumerate(stream, start=1):
        for token in tokenize(line):
            key = token.lower()
            if checker.is_correct(key):
                continue
            errors += 1
            if key not in seen:
                seen[key] = checker.suggest(key, n)
            hints = ", ".join(f"{w} ({d})" for w, d in seen[key]) or "no suggestions"
            print(f"{name}:{lineno}: '{token}' -> {hints}")
    return errors


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Spell checker using a hash table and Levenshtein distance.")
    parser.add_argument("files", nargs="*", help="text files to check (default: stdin)")
    parser.add_argument("-d", "--dictionary", default=DEFAULT_DICTIONARY,
                        help=f"word list, one word per line (default: {DEFAULT_DICTIONARY})")
    parser.add_argument("-n", "--num-suggestions", type=int, default=5,
                        help="suggestions per misspelled word (default: 5)")
    parser.add_argument("--damerau", action="store_true",
                        help="count adjacent swaps (e.g. 'ie'->'ei') as one edit")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print hash table statistics")
    args = parser.parse_args(argv)

    try:
        metric = damerau_levenshtein if args.damerau else levenshtein
        checker = SpellChecker.from_file(args.dictionary, metric)
    except OSError as exc:
        print(f"error: cannot read dictionary '{args.dictionary}': {exc}", file=sys.stderr)
        return 2

    if args.verbose:
        b, e, lf, longest = checker.table.stats()
        print(f"[hash table] buckets={b} entries={e} load={lf:.2f} longest_chain={longest}",
              file=sys.stderr)

    total = 0
    if args.files:
        for path in args.files:
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    total += check_stream(checker, fh, path, args.num_suggestions)
            except OSError as exc:
                print(f"error: cannot read '{path}': {exc}", file=sys.stderr)
                return 2
    else:
        total += check_stream(checker, sys.stdin, "<stdin>", args.num_suggestions)

    print(f"\n{total} misspelled word(s) found.", file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())