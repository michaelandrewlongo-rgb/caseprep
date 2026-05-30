from caseprep.core import EvidenceRecord
from caseprep.retrievers.papers_ask import citation_to_record


def test_citation_with_pmid_maps_to_record():
    cit = {
        "citation_number": 1,
        "pmid": "12345678",
        "doi": "10.1/abc",
        "title": "BP targets after thrombectomy",
        "journal": "Stroke",
        "pub_year": 2023,
        "primary_domain": "cerebrovascular",
        "study_type_hint": "rct",
        "evidence_source": "full_text",
        "passage_count": 3,
        "scores": {"rerank": 0.91},
    }
    rec = citation_to_record(cit)
    assert isinstance(rec, EvidenceRecord)
    assert rec.id == "papers-ask-12345678"
    assert rec.source == "papers"
    assert rec.title == "BP targets after thrombectomy"
    assert rec.metadata["pmid"] == "12345678"
    assert rec.metadata["doi"] == "10.1/abc"
    assert rec.metadata["year"] == 2023
    assert rec.metadata["retrieval_source"] == "papers_ask"
    assert rec.metadata["evidence_source"] == "full_text"
    assert rec.metadata["rerank"] == 0.91
    assert rec.metadata["provenance_key"] == "pmid"


def test_citation_without_ids_is_weak_key():
    cit = {
        "citation_number": 2,
        "pmid": "",
        "doi": "",
        "title": "Some OpenAlex-only work",
        "journal": "J Neurosurg",
        "pub_year": 2021,
        "primary_domain": "cerebrovascular",
        "study_type_hint": "cohort",
    }
    rec = citation_to_record(cit)
    assert rec.id == "papers-ask-some-openalex-only-work-2021"
    assert rec.metadata["provenance_key"] == "title_year_weak"
    assert rec.metadata["pmid"] == ""


def test_citation_doi_only_uses_doi_provenance_key():
    cit = {
        "pmid": "",
        "doi": "10.1016/j.example.2022.01.001",
        "title": "DOI only work",
        "pub_year": 2022,
    }
    rec = citation_to_record(cit)
    assert rec.metadata["provenance_key"] == "doi"
    assert rec.metadata["doi"] == "10.1016/j.example.2022.01.001"
    assert rec.id.startswith("papers-ask-10-1016")


def test_citation_missing_title_returns_none():
    assert citation_to_record({"pmid": "", "doi": "", "title": ""}) is None


def test_papers_record_dedups_against_pubmed_by_pmid():
    """A PAPERS citation sharing a PMID with another record collapses via the
    builder's existing metadata-pmid dedup."""
    from caseprep.core.builder import dedupe_evidence

    papers = citation_to_record({"pmid": "999", "doi": "", "title": "Shared",
                                 "pub_year": 2022})
    pubmed = EvidenceRecord(id="pubmed-999", source="pubmed", title="Shared",
                            text="abstract", metadata={"pmid": "999"})
    out = dedupe_evidence([pubmed, papers])
    assert len(out) == 1


def test_config_defaults_disabled(monkeypatch):
    from caseprep.retrievers.papers_ask import PapersAskConfig

    for k in ("CASEPREP_PAPERS_ENABLED", "CASEPREP_PAPERS_BASE_URL",
              "CASEPREP_PAPERS_AUTH", "CASEPREP_PAPERS_MAX_PAPERS",
              "CASEPREP_PAPERS_TIMEOUT_S", "CASEPREP_PAPERS_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    cfg = PapersAskConfig.from_env()
    assert cfg.enabled is False
    assert cfg.base_url == "http://127.0.0.1:8000"
    assert cfg.auth == "none"
    assert cfg.max_papers == 8
    assert cfg.timeout_s == 60


def test_config_reads_env(monkeypatch):
    from caseprep.retrievers.papers_ask import PapersAskConfig

    monkeypatch.setenv("CASEPREP_PAPERS_ENABLED", "1")
    monkeypatch.setenv("CASEPREP_PAPERS_BASE_URL", "http://host:9000/")
    monkeypatch.setenv("CASEPREP_PAPERS_AUTH", "cookie")
    monkeypatch.setenv("CASEPREP_PAPERS_PASSWORD", "neuro")
    monkeypatch.setenv("CASEPREP_PAPERS_MAX_PAPERS", "5")
    cfg = PapersAskConfig.from_env()
    assert cfg.enabled is True
    assert cfg.base_url == "http://host:9000"  # trailing slash stripped
    assert cfg.auth == "cookie"
    assert cfg.password == "neuro"
    assert cfg.max_papers == 5
