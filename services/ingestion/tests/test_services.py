import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.patient_linking import PatientLinkingService
from services.chunked_upload import ChunkedUploadManager
import pytest


def test_levenshtein_exact_match():
    service = PatientLinkingService()
    assert service._levenshtein_distance("ramesh", "ramesh") == 0


def test_levenshtein_one_edit():
    service = PatientLinkingService()
    assert service._levenshtein_distance("ramesh", "ramish") == 1


def test_levenshtein_empty():
    service = PatientLinkingService()
    assert service._levenshtein_distance("", "test") == 4
    assert service._levenshtein_distance("test", "") == 4


def test_name_similarity_exact():
    service = PatientLinkingService()
    score = service._compute_name_similarity("Ramesh Kumar", "Ramesh Kumar")
    assert score == 1.0


def test_name_similarity_reordered():
    service = PatientLinkingService()
    score = service._compute_name_similarity("Ramesh Kumar", "Kumar Ramesh")
    assert score == 1.0


def test_name_similarity_partial():
    service = PatientLinkingService()
    score = service._compute_name_similarity("Ramesh Kumar", "Ramesh K")
    assert score > 0.4


def test_name_similarity_completely_different():
    service = PatientLinkingService()
    score = service._compute_name_similarity("Ramesh Kumar", "Priya Sharma")
    assert score < 0.3


def test_name_similarity_empty():
    service = PatientLinkingService()
    score = service._compute_name_similarity("", "")
    assert score == 0.0


def test_name_similarity_case_insensitive():
    service = PatientLinkingService()
    score = service._compute_name_similarity("RAMESH KUMAR", "ramesh kumar")
    assert score == 1.0


def test_chunked_upload_init():
    manager = ChunkedUploadManager()
    result = manager.init_upload("test.pdf", 10_000_000, 2, "member-1", "application/pdf")

    assert "upload_id" in result
    assert result["total_chunks"] == 2


def test_chunked_upload_add_chunk():
    manager = ChunkedUploadManager()
    result = manager.init_upload("test.pdf", 100, 2, "member-1", "application/pdf")
    upload_id = result["upload_id"]

    chunk_result = manager.add_chunk(upload_id, 0, b"chunk_0_data")

    assert chunk_result["received_chunks"] == 1
    assert chunk_result["complete"] is False


def test_chunked_upload_complete_flow():
    manager = ChunkedUploadManager()
    result = manager.init_upload("test.pdf", 100, 2, "member-1", "application/pdf")
    upload_id = result["upload_id"]

    manager.add_chunk(upload_id, 0, b"chunk_0_data")
    manager.add_chunk(upload_id, 1, b"chunk_1_data")

    assert manager.is_complete(upload_id) is True

    assembled, metadata = manager.assemble(upload_id)

    assert assembled == b"chunk_0_data" + b"chunk_1_data"
    assert metadata["filename"] == "test.pdf"
    assert metadata["content_hash"] is not None
    assert metadata["total_size"] == len(assembled)


def test_chunked_upload_duplicate_chunk():
    manager = ChunkedUploadManager()
    result = manager.init_upload("test.pdf", 100, 2, "member-1", "application/pdf")
    upload_id = result["upload_id"]

    manager.add_chunk(upload_id, 0, b"data")

    with pytest.raises(ValueError, match="already received"):
        manager.add_chunk(upload_id, 0, b"data_again")


def test_chunked_upload_invalid_index():
    manager = ChunkedUploadManager()
    result = manager.init_upload("test.pdf", 100, 2, "member-1", "application/pdf")
    upload_id = result["upload_id"]

    with pytest.raises(ValueError, match="exceeds total"):
        manager.add_chunk(upload_id, 5, b"data")


def test_chunked_upload_assemble_incomplete():
    manager = ChunkedUploadManager()
    result = manager.init_upload("test.pdf", 100, 3, "member-1", "application/pdf")
    upload_id = result["upload_id"]

    manager.add_chunk(upload_id, 0, b"data")

    with pytest.raises(ValueError, match="Missing chunks"):
        manager.assemble(upload_id)


def test_chunked_upload_not_found():
    manager = ChunkedUploadManager()

    with pytest.raises(ValueError, match="not found"):
        manager.add_chunk("nonexistent", 0, b"data")


def test_chunked_upload_status():
    manager = ChunkedUploadManager()
    result = manager.init_upload("test.pdf", 100, 2, "member-1", "application/pdf")
    upload_id = result["upload_id"]

    status = manager.get_upload_status(upload_id)
    assert status["filename"] == "test.pdf"
    assert status["received_chunks"] == 0
    assert status["complete"] is False


def test_chunked_upload_cleanup():
    manager = ChunkedUploadManager()
    result = manager.init_upload("test.pdf", 100, 2, "member-1", "application/pdf")
    upload_id = result["upload_id"]

    manager.cleanup(upload_id)

    assert manager.get_upload_status(upload_id) is None


def test_chunked_upload_status_not_found():
    manager = ChunkedUploadManager()
    assert manager.get_upload_status("nonexistent") is None
