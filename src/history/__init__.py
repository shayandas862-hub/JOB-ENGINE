"""The system's memory: listing fingerprints, change events, deadline estimates.

dedupe_key is a listing's identity; content_fingerprint tracks what its content
looked like. When the two diverge between runs, a field-level event is recorded
in listing_events — appeared / changed / closed / reopened.
"""
