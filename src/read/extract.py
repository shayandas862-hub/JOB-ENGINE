"""Deterministic, free skill extraction (v1 — no API key needed).

Matches a curated skill dictionary against a job description and returns the
canonical skills found, each with a category. Matching is word-bounded and
case-insensitive. A Gemini-based extractor can replace/augment this later for
higher recall — the rest of the pipeline only depends on (canonical, category).
"""
from __future__ import annotations

import re

# canonical skill -> (category, [alias regex fragments, lowercase])
SKILL_DICT: dict[str, tuple[str, list[str]]] = {
    # --- programming ---
    "Python": ("programming", [r"python"]),
    "SQL": ("programming", [r"sql"]),
    "Java": ("programming", [r"java(?!script)"]),
    "Scala": ("programming", [r"scala"]),
    "JavaScript": ("programming", [r"javascript"]),
    "TypeScript": ("programming", [r"typescript"]),
    "Go": ("programming", [r"golang"]),
    "C++": ("programming", [r"c\+\+"]),
    "C#": ("programming", [r"c\#"]),
    "Rust": ("programming", [r"rust"]),
    "Bash": ("programming", [r"bash", r"shell scripting"]),
    # --- data engineering ---
    "Spark": ("data", [r"spark", r"pyspark"]),
    "Hadoop": ("data", [r"hadoop"]),
    "Kafka": ("data", [r"kafka"]),
    "Airflow": ("data", [r"airflow"]),
    "dbt": ("data", [r"dbt"]),
    "ETL": ("data", [r"etl", r"elt"]),
    "Data pipelines": ("data", [r"data pipelines?"]),
    "Data warehousing": ("data", [r"data warehous(e|ing)"]),
    "Databricks": ("data", [r"databricks"]),
    "Snowflake": ("data", [r"snowflake"]),
    "BigQuery": ("data", [r"bigquery", r"big query"]),
    "Redshift": ("data", [r"redshift"]),
    "Data modeling": ("data", [r"data model(ing|ling)"]),
    # --- cloud / devops ---
    "AWS": ("cloud", [r"aws", r"amazon web services"]),
    "Azure": ("cloud", [r"azure"]),
    "GCP": ("cloud", [r"gcp", r"google cloud"]),
    "Kubernetes": ("cloud", [r"kubernetes", r"k8s"]),
    "Docker": ("cloud", [r"docker"]),
    "Terraform": ("cloud", [r"terraform"]),
    "CI/CD": ("cloud", [r"ci/cd", r"ci cd"]),
    "Linux": ("cloud", [r"linux"]),
    "Microservices": ("cloud", [r"microservices?"]),
    "REST APIs": ("cloud", [r"rest api", r"restful", r"api integration"]),
    # --- ML / AI ---
    "Machine learning": ("ml", [r"machine learning", r"ml engineering"]),
    "Deep learning": ("ml", [r"deep learning"]),
    "NLP": ("ml", [r"nlp", r"natural language processing"]),
    "Computer vision": ("ml", [r"computer vision"]),
    "LLMs": ("ml", [r"llms?", r"large language models?"]),
    "Generative AI": ("ml", [r"generative ai", r"gen ?ai"]),
    "RAG": ("ml", [r"rag", r"retrieval[- ]augmented"]),
    "Prompt engineering": ("ml", [r"prompt engineering"]),
    "PyTorch": ("ml", [r"pytorch"]),
    "TensorFlow": ("ml", [r"tensorflow"]),
    "scikit-learn": ("ml", [r"scikit[- ]learn", r"sklearn"]),
    "MLOps": ("ml", [r"mlops"]),
    "Model deployment": ("ml", [r"model deployment", r"model serving"]),
    "Hugging Face": ("ml", [r"hugging ?face"]),
    "Fine-tuning": ("ml", [r"fine[- ]tuning"]),
    "Vector databases": ("ml", [r"vector databases?", r"vector db"]),
    "Embeddings": ("ml", [r"embeddings"]),
    "AI agents": ("ml", [r"ai agents?", r"agentic"]),
    # --- BI / viz ---
    "Tableau": ("bi", [r"tableau"]),
    "Power BI": ("bi", [r"power bi", r"powerbi"]),
    "Looker": ("bi", [r"looker"]),
    "Data visualisation": ("bi", [r"data visuali[sz]ation"]),
    # --- solutions / consulting / business ---
    "Solution architecture": ("solutions", [r"solutions? architect"]),
    "Pre-sales": ("solutions", [r"pre[- ]?sales"]),
    "Stakeholder management": ("solutions", [r"stakeholder"]),
    "Customer-facing": ("solutions", [r"customer[- ]facing", r"client[- ]facing"]),
    "Technical consulting": ("solutions", [r"technical consult"]),
    "Requirements gathering": ("solutions", [r"requirements (gathering|analysis)"]),
    "Solutions engineering": ("solutions", [r"solutions engineer", r"sales engineer"]),
    "Proof of concept": ("solutions", [r"proof[- ]of[- ]concept", r"\bpoc\b"]),
    "Customer success": ("solutions", [r"customer success"]),
    "Project management": ("solutions", [r"project management"]),
    "Agile": ("solutions", [r"agile", r"scrum"]),
    "Data analysis": ("solutions", [r"data analy(sis|tics)"]),
    "Business analysis": ("solutions", [r"business analy(sis|st)"]),
}


def _compile(dictionary):
    compiled = {}
    for canon, (cat, aliases) in dictionary.items():
        pats = [
            re.compile(r"(?<![A-Za-z0-9])(?:" + a + r")(?![A-Za-z0-9])", re.I)
            for a in aliases
        ]
        compiled[canon] = (cat, pats)
    return compiled


_COMPILED = _compile(SKILL_DICT)


def extract_skills(text: str | None) -> list[tuple[str, str]]:
    """Return [(canonical_skill, category)] found in the text (deduped, ordered)."""
    if not text:
        return []
    found: list[tuple[str, str]] = []
    for canon, (cat, pats) in _COMPILED.items():
        if any(p.search(text) for p in pats):
            found.append((canon, cat))
    return found
