"""Named saved watches — standing filter combinations, evaluated nightly.

`plans/0011`, built as item 5 of Phase 9.5. A watch is an AND of any of ten
dimensions; an owner's watch list is an OR of watches. That algebra is
complete: by disjunctive normal form any nested AND/OR expression rewrites
into a plain list of AND-only watches, so richer combinators would add zero
expressive power and only unexplainable receipts.

Nothing here calls AI. Yield prediction, the too-tight/too-loose advice and
the overlap warning are all counted by REPLAYING a watch over stored history —
the replayed rows are the receipts, which is why a watch can say "~2.3 a week
(11 real examples)" instead of an opinion.
"""
