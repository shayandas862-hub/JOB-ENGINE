"""The public status page — the one surface anyone may read without a token.

Person-free by construction: the package reads only the curated views from
migration 0043, and those views are the privacy boundary. Nothing here knows
the name of a personal column, so nothing here can leak one (a test checks the
source for exactly that). Adding a fact to this page means adding it to the
VIEW first, and asking whether a stranger should see it.
"""
