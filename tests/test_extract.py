from read.extract import extract_skills


def canon(text):
    return {c for c, _ in extract_skills(text)}


def test_basic_tech_stack():
    s = canon("We use Python and Spark on AWS with Kubernetes, plus SQL.")
    assert {"Python", "Spark", "AWS", "Kubernetes", "SQL"} <= s


def test_ml_terms():
    s = canon("Experience with machine learning, LLMs and RAG pipelines; prompt engineering a plus.")
    assert {"Machine learning", "LLMs", "RAG", "Prompt engineering"} <= s


def test_category_returned():
    pairs = dict(extract_skills("Strong Python and machine learning background."))
    assert pairs["Python"] == "programming"
    assert pairs["Machine learning"] == "ml"


def test_no_false_positive_java_in_javascript():
    s = canon("Strong JavaScript skills required.")
    assert "JavaScript" in s
    assert "Java" not in s


def test_no_false_positive_rag_substring():
    s = canon("They drag and drop files into storage.")
    assert "RAG" not in s


def test_empty():
    assert extract_skills("") == []
    assert extract_skills(None) == []


def test_unread_roles_picker_reads_only_local_listings():
    # The paid reader must never see a foreign JD by accident (keep-all stores
    # them; the extractor picker — the cost cage — narrows to is_local).
    from persist.extract_rules import UNREAD_ROLES_SQL
    low = UNREAD_ROLES_SQL.lower()
    assert "extracted_at is null" in low
    assert "is_local" in low
