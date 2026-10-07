"""
Phase 0 Tests: Dataset Profile Verification
============================================
Tests for the dataset profiler (benchmark/dataset/profile.py).

Run with:
    pytest benchmark/tests/test_dataset_profile.py -v
from the project root.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure project root is in sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Try to import the profiler module
try:
    from benchmark.dataset import profile as profiler_module
    IMPORT_SUCCESS = True
except ImportError as _import_err:
    IMPORT_SUCCESS = False
    _import_err_msg = str(_import_err)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def corpus_path() -> Path:
    """Return the corpus.jsonl path."""
    p = PROJECT_ROOT / "corpus.jsonl"
    if not p.exists():
        pytest.skip(f"corpus.jsonl not found at {p}")
    return p


@pytest.fixture(scope="session")
def eval_public_path() -> Path:
    """Return the eval_public.jsonl path."""
    p = PROJECT_ROOT / "eval_public.jsonl"
    if not p.exists():
        pytest.skip(f"eval_public.jsonl not found at {p}")
    return p


@pytest.fixture(scope="session")
def eval_hidden_path() -> Path:
    """Return the eval_hidden.jsonl path."""
    p = PROJECT_ROOT / "eval_hidden.jsonl"
    if not p.exists():
        pytest.skip(f"eval_hidden.jsonl not found at {p}")
    return p


@pytest.fixture(scope="session")
def output_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return a temporary output path for the profile JSON."""
    return tmp_path_factory.mktemp("dataset") / "dataset_profile.json"


@pytest.fixture(scope="session")
def full_profile(corpus_path, eval_public_path, eval_hidden_path, output_path):
    """Generate the full profile once per test session."""
    if not IMPORT_SUCCESS:
        pytest.skip(f"Cannot import profiler: {_import_err_msg}")
    profile = profiler_module.generate_profile(
        corpus_path=corpus_path,
        eval_public_path=eval_public_path,
        eval_hidden_path=eval_hidden_path,
        output_path=output_path,
    )
    return profile


# ---------------------------------------------------------------------------
# Import Tests
# ---------------------------------------------------------------------------

class TestImport:
    """Verify that the profiler module can be imported."""

    def test_import_succeeds(self) -> None:
        """Profiler module must import without errors."""
        assert IMPORT_SUCCESS, f"Import failed: {_import_err_msg if not IMPORT_SUCCESS else ''}"

    def test_generate_profile_exists(self) -> None:
        """generate_profile function must exist."""
        if not IMPORT_SUCCESS:
            pytest.skip("Module import failed")
        assert hasattr(profiler_module, "generate_profile"), (
            "profiler_module missing generate_profile function"
        )

    def test_profile_corpus_exists(self) -> None:
        """profile_corpus function must exist."""
        if not IMPORT_SUCCESS:
            pytest.skip("Module import failed")
        assert hasattr(profiler_module, "profile_corpus")

    def test_profile_eval_public_exists(self) -> None:
        """profile_eval_public function must exist."""
        if not IMPORT_SUCCESS:
            pytest.skip("Module import failed")
        assert hasattr(profiler_module, "profile_eval_public")

    def test_profile_eval_hidden_exists(self) -> None:
        """profile_eval_hidden function must exist."""
        if not IMPORT_SUCCESS:
            pytest.skip("Module import failed")
        assert hasattr(profiler_module, "profile_eval_hidden")


# ---------------------------------------------------------------------------
# Profile Structure Tests
# ---------------------------------------------------------------------------

class TestProfileStructure:
    """Verify profile output has the expected top-level keys."""

    def test_profile_has_corpus_key(self, full_profile) -> None:
        """Profile must have a 'corpus' key."""
        assert "corpus" in full_profile

    def test_profile_has_eval_public_key(self, full_profile) -> None:
        """Profile must have an 'eval_public' key."""
        assert "eval_public" in full_profile

    def test_profile_has_eval_hidden_key(self, full_profile) -> None:
        """Profile must have an 'eval_hidden' key."""
        assert "eval_hidden" in full_profile

    def test_profile_has_schema_version(self, full_profile) -> None:
        """Profile must have a schema version."""
        assert "schema_version" in full_profile

    def test_profile_has_phase(self, full_profile) -> None:
        """Profile must record the phase number."""
        assert full_profile.get("phase") == "0"


# ---------------------------------------------------------------------------
# Corpus Count Tests
# ---------------------------------------------------------------------------

class TestCorpusProfile:
    """Verify corpus statistics match known dataset facts."""

    def test_corpus_document_count(self, full_profile) -> None:
        """Corpus must contain exactly 2,951 documents."""
        assert full_profile["corpus"]["total_documents"] == 2951, (
            f"Expected 2951 docs, got {full_profile['corpus']['total_documents']}"
        )

    def test_corpus_no_duplicate_ids(self, full_profile) -> None:
        """Corpus should have no duplicate document IDs."""
        dups = full_profile["corpus"]["duplicate_id_count"]
        assert dups == 0, f"Found {dups} duplicate document IDs"

    def test_corpus_has_fields_key(self, full_profile) -> None:
        """Corpus profile must include field analysis."""
        assert "fields" in full_profile["corpus"]

    def test_corpus_expected_fields_present(self, full_profile) -> None:
        """All expected corpus fields must appear in field analysis."""
        expected = ["doc_id", "title", "url", "text", "approx_tokens"]
        for field in expected:
            assert field in full_profile["corpus"]["fields"], (
                f"Missing field analysis for '{field}'"
            )

    def test_corpus_text_length_distribution(self, full_profile) -> None:
        """Text length distribution must be present and non-zero."""
        dist = full_profile["corpus"]["text_length_distribution"]
        assert dist["count"] == 2951
        assert dist["mean"] > 0

    def test_corpus_approx_tokens_distribution(self, full_profile) -> None:
        """Approx token distribution must be present."""
        dist = full_profile["corpus"]["approx_tokens_distribution"]
        assert dist["count"] > 0
        assert dist["min"] > 0


# ---------------------------------------------------------------------------
# Public Eval Tests
# ---------------------------------------------------------------------------

class TestEvalPublicProfile:
    """Verify public evaluation set statistics."""

    def test_public_question_count(self, full_profile) -> None:
        """Public eval must contain exactly 100 questions."""
        count = full_profile["eval_public"]["total_questions"]
        assert count == 100, f"Expected 100 questions, got {count}"

    def test_public_has_qtypes(self, full_profile) -> None:
        """Public eval must report question type distribution."""
        qtypes = full_profile["eval_public"]["question_type_distribution"]
        assert len(qtypes) > 0, "No question types found"

    def test_public_aggregation_qtype_present(self, full_profile) -> None:
        """'aggregation' question type must be present in public eval."""
        qtypes = full_profile["eval_public"]["question_type_distribution"]
        assert "aggregation" in qtypes, (
            f"Expected 'aggregation' qtype, found: {list(qtypes.keys())}"
        )

    def test_public_no_duplicate_qids(self, full_profile) -> None:
        """Public eval must have no duplicate question IDs."""
        dups = full_profile["eval_public"]["duplicate_qid_count"]
        assert dups == 0, f"Found {dups} duplicate QIDs"

    def test_public_question_lengths_positive(self, full_profile) -> None:
        """All questions must have positive length."""
        dist = full_profile["eval_public"]["question_length_distribution"]
        assert dist["min"] > 0, "Empty questions found"

    def test_public_gold_doc_analysis(self, full_profile) -> None:
        """Gold doc count distribution must be present."""
        dist = full_profile["eval_public"]["gold_doc_count_distribution"]
        assert dist["count"] == 100


# ---------------------------------------------------------------------------
# Hidden Eval Tests
# ---------------------------------------------------------------------------

class TestEvalHiddenProfile:
    """Verify hidden evaluation set security and structure."""

    def test_hidden_question_count(self, full_profile) -> None:
        """Hidden eval must contain exactly 50 questions."""
        count = full_profile["eval_hidden"]["total_questions"]
        assert count == 50, f"Expected 50 hidden questions, got {count}"

    def test_hidden_no_answer_field(self, full_profile) -> None:
        """Hidden eval profile must NOT contain a raw 'answers' key."""
        hidden = full_profile["eval_hidden"]
        assert "answers" not in hidden, "Hidden answers must never be stored in profile"
        assert "gold_doc_ids" not in hidden, "Hidden gold_doc_ids must never be stored in profile"

    def test_hidden_available_fields_safe(self, full_profile) -> None:
        """Hidden eval must only report safe structural fields."""
        safe_fields = {"qid", "question", "qtype"}
        available = set(full_profile["eval_hidden"].get("available_fields", []))
        unsafe = available - safe_fields
        assert len(unsafe) == 0, f"Unsafe fields found in hidden profile: {unsafe}"

    def test_hidden_has_qtypes(self, full_profile) -> None:
        """Hidden eval must report question type distribution."""
        qtypes = full_profile["eval_hidden"]["question_type_distribution"]
        assert len(qtypes) > 0

    def test_hidden_security_note_present(self, full_profile) -> None:
        """Hidden profile must include a security note."""
        assert "security_note" in full_profile["eval_hidden"]


# ---------------------------------------------------------------------------
# Output File Tests
# ---------------------------------------------------------------------------

class TestProfileOutput:
    """Verify the output file is valid and complete."""

    def test_output_file_created(self, output_path, full_profile) -> None:
        """Output profile JSON file must exist."""
        assert output_path.exists(), f"Profile file not created at {output_path}"

    def test_output_file_valid_json(self, output_path, full_profile) -> None:
        """Output file must be valid JSON."""
        with output_path.open(encoding="utf-8") as fh:
            loaded = json.load(fh)
        assert isinstance(loaded, dict)

    def test_output_file_matches_profile(self, output_path, full_profile) -> None:
        """Output file must match the returned profile."""
        with output_path.open(encoding="utf-8") as fh:
            loaded = json.load(fh)
        assert loaded["corpus"]["total_documents"] == full_profile["corpus"]["total_documents"]


# ---------------------------------------------------------------------------
# Streaming Tests
# ---------------------------------------------------------------------------

class TestStreaming:
    """Verify the streaming helper works correctly."""

    def test_stream_jsonl_yields_objects(self, corpus_path) -> None:
        """_stream_jsonl must yield dicts from corpus.jsonl."""
        if not IMPORT_SUCCESS:
            pytest.skip("Module import failed")
        count = 0
        for obj in profiler_module._stream_jsonl(corpus_path):
            assert isinstance(obj, dict)
            count += 1
            if count >= 5:
                break
        assert count == 5

    def test_stream_jsonl_file_not_found(self) -> None:
        """_stream_jsonl must raise FileNotFoundError for missing files."""
        if not IMPORT_SUCCESS:
            pytest.skip("Module import failed")
        with pytest.raises(FileNotFoundError):
            list(profiler_module._stream_jsonl(Path("/nonexistent/file.jsonl")))
