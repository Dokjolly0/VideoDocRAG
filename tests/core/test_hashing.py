import hashlib

import pytest

from videodoc.core.utils.hashing import hash_file


def test_hash_file_matches_reference_digest(tmp_path):
    path = tmp_path / "a.bin"
    content = b"hello world"
    path.write_bytes(content)
    assert hash_file(path) == hashlib.sha256(content).hexdigest()


def test_hash_file_chunking_does_not_change_result(tmp_path):
    path = tmp_path / "big.bin"
    content = b"x" * (3 * 1024 + 7)  # not a clean multiple of chunk_size
    path.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    assert hash_file(path, chunk_size=1024) == expected
    assert hash_file(path, chunk_size=64) == expected


def test_hash_file_missing_raises_oserror(tmp_path):
    with pytest.raises(OSError):
        hash_file(tmp_path / "does-not-exist.bin")


def test_hash_file_reports_increasing_progress(tmp_path):
    path = tmp_path / "big.bin"
    path.write_bytes(b"x" * 300)

    fractions = []
    hash_file(path, chunk_size=100, progress_callback=fractions.append)

    assert fractions == [pytest.approx(1 / 3), pytest.approx(2 / 3), pytest.approx(1.0)]


def test_hash_file_empty_file_never_calls_progress_callback(tmp_path):
    path = tmp_path / "empty.bin"
    path.write_bytes(b"")

    fractions = []
    hash_file(path, progress_callback=fractions.append)

    assert fractions == []
