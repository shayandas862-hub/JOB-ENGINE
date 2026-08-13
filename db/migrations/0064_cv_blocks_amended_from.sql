-- 0064 · Phase 9.5 task 2 (M6) — an amendment is a LINK, not an edit.
--
-- Correcting a fact was already possible as retire + re-add, and keep-all made
-- that correct: the old wording survives, stamped. What it lost was the
-- relationship. Two rows sat side by side with nothing saying the second was
-- the first one's correction, so "what did this fact used to say?" could only
-- be answered by guessing from timestamps.
--
-- This column is the chain. It is deliberately NOT a status, and there is
-- deliberately no reverse pointer: the old row is never touched again after
-- its retirement stamp, so a `superseded_by` written onto it would mean going
-- back and modifying a retired row — the exact mutation the stamp chain
-- exists to avoid. The arrow points backwards, from the new row to the one it
-- replaces, and it is written once at insert.
--
-- Nullable, because most blocks are not amendments and never will be.
-- Self-referencing FK so a chain can be walked, and ON DELETE is not
-- specified because nothing in this schema deletes a cv_block — removals are
-- stamps, and a delete here should fail loudly rather than orphan a chain.
--
-- Verified after applying: column present and nullable; get_advisors reports
-- no new finding (3 pre-existing WARNs unchanged).
BEGIN;

ALTER TABLE public.cv_blocks
  ADD COLUMN IF NOT EXISTS amended_from bigint REFERENCES public.cv_blocks(block_id);

COMMENT ON COLUMN public.cv_blocks.amended_from IS
  'The block this one corrects (M6). Written once, at insert, by cv.amend. '
  'The superseded row keeps its exact wording and its confirmed state — its '
  'retirement stamp is the only thing that changes — so the chain records '
  'what a fact used to say, not merely that it changed.';

COMMIT;
