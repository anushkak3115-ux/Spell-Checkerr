# Spell Checker

This is a command-line spell checker I wrote in Python for my data structures class. It reads a dictionary into a hash table, checks every word in a text against it, and suggests the closest words for anything it doesn't find.

## Running it

You need Python 3 and nothing else.

    python3 spellchecker.py test.txt

If you don't give it a file, it reads from the keyboard, so you can also do this:

    echo "helo wrld" | python3 spellchecker.py

Options:

- `-d words.txt` picks the dictionary file (one word per line). If you skip it, the program uses `/usr/share/dict/words`, which exists on Macs.
- `-n 3` changes how many suggestions you get per word. The default is 5.
- `--damerau` counts swapped neighbouring letters as one mistake instead of two (more on that below).
- `-v` prints some stats about the hash table.

Example output:

    test.txt:1: 'spel' -> spell (1), held (3), hell (3)
    test.txt:1: 'wrld' -> world (1), held (2), word (2)

The number in brackets is the edit distance. The program exits with 0 if everything was spelled right, 1 if it found mistakes, and 2 if it couldn't open a file.

## How it works

**Hash table.** I wrote the hash table myself instead of using Python's `dict` or `set`. It's an array of buckets, and each bucket is a linked list. If two words land in the same bucket they just get chained together. For the hash function I used FNV-1a, because it's short and spreads words out well. When the table gets more than 75% full it doubles in size and moves everything over, so the chains stay short and lookups stay fast.

**Levenshtein distance.** This counts the fewest inserts, deletes and substitutions needed to turn one word into another. "kitten" to "sitting" is 3, for example. I used the usual table-filling method, but only keep two rows at a time since that's all it needs. I also added a cutoff: once a word can't possibly beat the suggestions I already have, it stops early.

**Suggestions.** If a word isn't in the table, the program goes through every dictionary word, measures the distance, and keeps the best few. Words with the same distance are sorted alphabetically so the output is the same every time. If the same typo shows up twice, it only calculates it once.

**Cleaning up the input.** Everything is lowercased, so "Hello" and "hello" count as the same word. Punctuation and numbers are ignored. Apostrophes inside words are kept, so "don't" works.

## Speed

Checking one word takes O(1) on average because of the hash table. Without it I'd have to scan the whole dictionary for every word, which is O(n). Only misspelled words trigger the slow suggestion search, which compares against every dictionary word and costs roughly O(n * L^2) where L is the word length. The cutoff makes it a lot quicker in practice.

## The --damerau option

Normal Levenshtein treats a swap like "ie" to "ei" as two edits (one delete and one insert). That's a bit unfair for typos, because swapping two letters is really common. With `--damerau`, a swap counts as one edit. For example, "chekcer" is 2 away from "checker" normally, but 1 away with the flag, so "checker" comes first in the list.

## Things that could be better

- The suggestion search checks every word, so it gets slow on huge dictionaries. A BK-tree would fix that.
- It doesn't care how common a word is, so a weird word can show up above a common one with the same distance.
- Hyphenated words get split and checked as separate words.

## Files

- `spellchecker.py` is the program.
- `words.txt` is a small dictionary for testing.
- `test.txt` is a sample file with a few typos.
