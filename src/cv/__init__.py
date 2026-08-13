"""CV maker — tailored, ATS-friendly CVs from verified career facts.

Every line a CV ships must trace to a confirmed fact in cv_blocks: assemble.py
selects and orders blocks by skill evidence, Gemini (caged) rephrases only the
fact text, and a truth gate rejects anything untraceable, falling back to the
grounded blocks. render.py writes the ATS-safe .docx.
"""
