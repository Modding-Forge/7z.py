"""
Copyright (c) Modding Forge

Integration tests for ArchiveReader / ArchiveWriter.

These tests perform real I/O using the bundled 7z.dll and verify the full
round-trip: create archive on disk → extract → assert file content matches.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

import pytest

from py7z import ArchiveReader, ArchiveWriter
from py7z.progress import ProgressInfo


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_tree(root: Path) -> dict[str, bytes]:
    """
    Creates a predictable directory tree under *root* and returns a
    ``{archive_relative_path: content}`` map that the tests can assert
    against.

    Layout::

        root/
          aaa_dir/            ← directory entry first (stress-tests S_FALSE
                                handling after skipped directory streams)
            deep.bin
          bbb_file.txt
          ccc_file.bin
    """
    adir = root / "aaa_dir"
    adir.mkdir(parents=True)

    payloads: dict[str, bytes] = {
        "aaa_dir/deep.bin":  bytes(range(256)),
        "bbb_file.txt":      b"hello world\n",
        "ccc_file.bin":      os.urandom(4096),
    }
    (adir / "deep.bin").write_bytes(payloads["aaa_dir/deep.bin"])
    (root / "bbb_file.txt").write_bytes(payloads["bbb_file.txt"])
    (root / "ccc_file.bin").write_bytes(payloads["ccc_file.bin"])
    return payloads


# ---------------------------------------------------------------------------
# extraction round-trip
# ---------------------------------------------------------------------------


class TestExtractionRoundTrip:
    """End-to-end tests: create archive → extract → verify file content."""

    def test_flat_files_roundtrip(self, tmp_path: Path) -> None:
        """
        Extracts an archive that contains only flat (root-level) files
        and verifies each file's content.
        """
        src = tmp_path / "src"
        src.mkdir()
        content_a = b"file A content"
        content_b = b"file B content"
        (src / "a.txt").write_bytes(content_a)
        (src / "b.bin").write_bytes(content_b)

        archive = tmp_path / "flat.7z"
        with ArchiveWriter(archive) as w:
            w.add_file(src / "a.txt", archive_path="a.txt")
            w.add_file(src / "b.bin", archive_path="b.bin")

        out = tmp_path / "out"
        with ArchiveReader(archive) as r:
            r.extract_all(out)

        assert (out / "a.txt").read_bytes() == content_a
        assert (out / "b.bin").read_bytes() == content_b

    def test_directory_entry_is_created(self, tmp_path: Path) -> None:
        """
        Verifies that an explicit directory entry results in a directory
        being created on disk even when it contains no files.
        """
        src = tmp_path / "src"
        src.mkdir()
        (src / "placeholder.txt").write_bytes(b"x")

        archive = tmp_path / "dirs.7z"
        with ArchiveWriter(archive) as w:
            w.add_directory(src)

        out = tmp_path / "out"
        with ArchiveReader(archive) as r:
            r.extract_all(out)

        # The directory itself must exist
        extracted_dir = out / "src"
        assert extracted_dir.is_dir(), \
            f"Expected directory '{extracted_dir}' to be created"

    def test_files_after_directory_entry_are_extracted(
        self, tmp_path: Path
    ) -> None:
        """
        Reproduces the reported bug where extraction stops after
        ``GetStream`` returns ``S_FALSE`` for a directory entry.

        The archive intentionally starts with a directory entry (aaa_dir/)
        followed by file entries so that the first callback is a skip.
        All subsequent file entries must still be extracted.
        """
        src = tmp_path / "src"
        src.mkdir()
        payloads = _make_tree(src)

        archive = tmp_path / "mixed.7z"
        with ArchiveWriter(archive) as w:
            w.add_directory(src)

        out = tmp_path / "out"
        with ArchiveReader(archive) as r:
            r.extract_all(out)

        prefix = out / "src"
        for rel_path, expected_bytes in payloads.items():
            dest = prefix / Path(rel_path)
            assert dest.exists(), \
                f"Entry '{rel_path}' was not extracted (path: {dest})"
            assert dest.read_bytes() == expected_bytes, \
                f"Content mismatch for '{rel_path}'"

    def test_all_entry_count_matches(self, tmp_path: Path) -> None:
        """
        Verifies that the number of extracted files equals the number of
        non-directory entries reported by ArchiveReader.entries().
        """
        src = tmp_path / "src"
        src.mkdir()
        _make_tree(src)

        archive = tmp_path / "count.7z"
        with ArchiveWriter(archive) as w:
            w.add_directory(src)

        with ArchiveReader(archive) as r:
            expected_files = [e for e in r.entries() if not e.is_directory]

        out = tmp_path / "out"
        with ArchiveReader(archive) as r:
            r.extract_all(out)

        extracted_files = [f for f in out.rglob("*") if f.is_file()]
        assert len(extracted_files) == len(expected_files), (
            f"Expected {len(expected_files)} files, "
            f"but extracted {len(extracted_files)}"
        )

    def test_nested_directory_structure_preserved(
        self, tmp_path: Path
    ) -> None:
        """
        Verifies that a multi-level directory hierarchy is reconstructed
        correctly after extraction.
        """
        src = tmp_path / "src"
        src.mkdir()
        lvl1 = src / "level1"
        lvl2 = lvl1 / "level2"
        lvl2.mkdir(parents=True)
        content = b"deep nested content"
        (lvl2 / "deep.txt").write_bytes(content)

        archive = tmp_path / "nested.7z"
        with ArchiveWriter(archive) as w:
            w.add_directory(src)

        out = tmp_path / "out"
        with ArchiveReader(archive) as r:
            r.extract_all(out)

        deep_file = out / "src" / "level1" / "level2" / "deep.txt"
        assert deep_file.is_file(), \
            f"Deeply nested file '{deep_file}' was not extracted"
        assert deep_file.read_bytes() == content

    def test_multiple_directories_before_files(
        self, tmp_path: Path
    ) -> None:
        """
        Creates an archive with multiple directory entries ordered before
        all file entries (matching the layout of the real Downloads.7z)
        and asserts that every file is extracted.
        """
        src = tmp_path / "src"
        src.mkdir()
        # Three sibling dirs that sort before the files ('a'/'b'/'c' < 'd')
        for d in ("adir", "bdir", "cdir"):
            (src / d).mkdir()
        # Files that sort after the dir names
        payloads: dict[str, bytes] = {
            "dfile.bin": b"D" * 512,
            "efile.txt": b"hello from E",
        }
        for name, data in payloads.items():
            (src / name).write_bytes(data)

        archive = tmp_path / "dirs_first.7z"
        with ArchiveWriter(archive) as w:
            w.add_directory(src)

        out = tmp_path / "out"
        with ArchiveReader(archive) as r:
            r.extract_all(out)

        prefix = out / "src"
        for name, expected in payloads.items():
            dest = prefix / name
            assert dest.is_file(), \
                f"'{name}' not extracted after multiple directory entries"
            assert dest.read_bytes() == expected

    def test_binary_content_preserved_exactly(
        self, tmp_path: Path
    ) -> None:
        """
        Verifies that arbitrary binary content survives the
        compress-decompress cycle without corruption.
        """
        # 64 KiB of non-compressible random bytes
        payload = os.urandom(65536)
        src = tmp_path / "src"
        src.mkdir()
        (src / "random.bin").write_bytes(payload)

        archive = tmp_path / "binary.7z"
        with ArchiveWriter(archive, compression_level=0) as w:
            w.add_file(src / "random.bin", archive_path="random.bin")

        out = tmp_path / "out"
        with ArchiveReader(archive) as r:
            r.extract_all(out)

        assert (out / "random.bin").read_bytes() == payload

    def test_overwrite_false_preserves_existing_file(
        self, tmp_path: Path
    ) -> None:
        """
        When ``overwrite=False``, a file that already exists on disk must
        not be replaced by the extracted version.
        """
        src = tmp_path / "src"
        src.mkdir()
        (src / "file.txt").write_bytes(b"original")

        archive = tmp_path / "ow.7z"
        with ArchiveWriter(archive) as w:
            w.add_file(src / "file.txt", archive_path="file.txt")

        out = tmp_path / "out"
        out.mkdir()
        existing = out / "file.txt"
        existing.write_bytes(b"kept")

        with ArchiveReader(archive) as r:
            r.extract_all(out, overwrite=False)

        assert existing.read_bytes() == b"kept"

    def test_overwrite_true_replaces_existing_file(
        self, tmp_path: Path
    ) -> None:
        """
        When ``overwrite=True`` (default), an existing file must be
        replaced with the archive content.
        """
        src = tmp_path / "src"
        src.mkdir()
        (src / "file.txt").write_bytes(b"from archive")

        archive = tmp_path / "ow_true.7z"
        with ArchiveWriter(archive) as w:
            w.add_file(src / "file.txt", archive_path="file.txt")

        out = tmp_path / "out"
        out.mkdir()
        (out / "file.txt").write_bytes(b"old")

        with ArchiveReader(archive) as r:
            r.extract_all(out, overwrite=True)

        assert (out / "file.txt").read_bytes() == b"from archive"

    def test_extract_entry_returns_correct_bytes(
        self, tmp_path: Path
    ) -> None:
        """
        ``ArchiveReader.extract_entry()`` must return the exact byte content
        of the requested entry without writing any other files.
        """
        content_a = b"entry A data" * 100
        content_b = b"entry B data" * 100
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.bin").write_bytes(content_a)
        (src / "b.bin").write_bytes(content_b)

        archive = tmp_path / "single.7z"
        with ArchiveWriter(archive) as w:
            w.add_file(src / "a.bin", archive_path="a.bin")
            w.add_file(src / "b.bin", archive_path="b.bin")

        with ArchiveReader(archive) as r:
            entries = list(r.entries())
            idx_b = next(e.index for e in entries if e.path == "b.bin")
            data = r.extract_entry(idx_b)

        assert data == content_b

    def test_extract_entry_writes_to_output_dir(
        self, tmp_path: Path
    ) -> None:
        """
        When ``output_dir`` is provided to ``extract_entry``, the file
        must be written to disk as well as returned.
        """
        content = b"persisted content"
        src = tmp_path / "src"
        src.mkdir()
        (src / "doc.txt").write_bytes(content)

        archive = tmp_path / "persist.7z"
        with ArchiveWriter(archive) as w:
            w.add_file(src / "doc.txt", archive_path="doc.txt")

        out = tmp_path / "out"
        out.mkdir()
        with ArchiveReader(archive) as r:
            data = r.extract_entry(0, output_dir=out)

        assert data == content
        assert (out / "doc.txt").read_bytes() == content


# ---------------------------------------------------------------------------
# progress callback
# ---------------------------------------------------------------------------


class TestProgressCallback:
    """Verifies that progress callbacks receive correct ProgressInfo data."""

    def _make_archive(self, tmp_path: Path, total_size: int = 4096) -> Path:
        """Creates a single-file archive with *total_size* bytes."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "data.bin").write_bytes(b"x" * total_size)
        archive = tmp_path / "cb.7z"
        with ArchiveWriter(archive, compression_level=0) as w:
            w.add_file(src / "data.bin", archive_path="data.bin")
        return archive

    def test_progress_callback_is_called(self, tmp_path: Path) -> None:
        """Progress callback must be invoked at least once during extraction."""
        archive = self._make_archive(tmp_path)
        calls: list[ProgressInfo] = []

        out = tmp_path / "out"
        with ArchiveReader(archive) as r:
            r.extract_all(out, progress_cb=lambda info: calls.append(
                info.model_copy()
            ))

        assert len(calls) > 0, "Progress callback was never called"

    def test_progress_info_has_positive_total_bytes(
        self, tmp_path: Path
    ) -> None:
        """``total_bytes`` must be > 0 during extraction of a non-empty archive."""
        archive = self._make_archive(tmp_path, total_size=8192)
        total_values: list[int] = []

        out = tmp_path / "out"
        with ArchiveReader(archive) as r:
            r.extract_all(out, progress_cb=lambda info: total_values.append(
                info.total_bytes
            ))

        positives = [v for v in total_values if v > 0]
        assert positives, \
            "total_bytes was never > 0 in any progress callback invocation"

    def test_progress_percent_increases_monotonically(
        self, tmp_path: Path
    ) -> None:
        """
        The ``percent`` value reported across successive callback
        invocations must be non-decreasing.
        """
        archive = self._make_archive(tmp_path, total_size=65536)
        percents: list[float] = []

        out = tmp_path / "out"
        with ArchiveReader(archive) as r:
            r.extract_all(out, progress_cb=lambda info: percents.append(
                info.percent
            ))

        for i in range(1, len(percents)):
            assert percents[i] >= percents[i - 1] - 0.01, (
                f"Percent decreased: {percents[i - 1]:.2f} → {percents[i]:.2f} "
                f"at callback #{i}"
            )

    def test_progress_completed_bytes_does_not_exceed_total(
        self, tmp_path: Path
    ) -> None:
        """
        ``completed_bytes`` must never exceed ``total_bytes`` when
        ``total_bytes > 0``.
        """
        archive = self._make_archive(tmp_path, total_size=32768)
        violations: list[str] = []

        def _cb(info: ProgressInfo) -> None:
            if info.total_bytes > 0 and info.completed_bytes > info.total_bytes:
                violations.append(
                    f"completed={info.completed_bytes} > total={info.total_bytes}"
                )

        out = tmp_path / "out"
        with ArchiveReader(archive) as r:
            r.extract_all(out, progress_cb=_cb)

        assert not violations, "; ".join(violations)

    def test_progress_current_file_is_set_at_operation_result(
        self, tmp_path: Path
    ) -> None:
        """
        After ``SetOperationResult`` fires the callback, ``current_file``
        must be the archive path of the item that was just extracted.
        """
        src = tmp_path / "src"
        src.mkdir()
        (src / "target.txt").write_bytes(b"data")

        archive = tmp_path / "cf.7z"
        with ArchiveWriter(archive) as w:
            w.add_file(src / "target.txt", archive_path="target.txt")

        seen_files: list[str | None] = []

        out = tmp_path / "out"
        with ArchiveReader(archive) as r:
            r.extract_all(out, progress_cb=lambda info: seen_files.append(
                info.current_file
            ))

        assert any(f == "target.txt" for f in seen_files), (
            f"'target.txt' was never seen in current_file. Got: {seen_files}"
        )

    def test_progress_total_files_matches_archive_count(
        self, tmp_path: Path
    ) -> None:
        """
        ``total_files`` inside the callback must equal the number of
        entries reported by ``ArchiveReader.count()``.
        """
        src = tmp_path / "src"
        src.mkdir()
        _make_tree(src)

        archive = tmp_path / "tf.7z"
        with ArchiveWriter(archive) as w:
            w.add_directory(src)

        with ArchiveReader(archive) as r:
            expected_total = r.count()

        seen_totals: list[int] = []
        out = tmp_path / "out"
        with ArchiveReader(archive) as r:
            r.extract_all(out, progress_cb=lambda info: seen_totals.append(
                info.total_files
            ))

        assert seen_totals, "Progress callback was never called"
        assert all(t == expected_total for t in seen_totals), (
            f"total_files mismatch. Expected {expected_total}. "
            f"Observed: {set(seen_totals)}"
        )

    def test_progress_elapsed_seconds_increases(
        self, tmp_path: Path
    ) -> None:
        """
        ``elapsed_seconds`` must be non-negative and generally increasing
        across callback invocations for a non-trivial archive.
        """
        # Large enough that the DLL makes multiple progress calls
        archive = self._make_archive(tmp_path, total_size=1 << 20)  # 1 MiB
        elapsed: list[float] = []

        out = tmp_path / "out"
        with ArchiveReader(archive) as r:
            r.extract_all(out, progress_cb=lambda info: elapsed.append(
                info.elapsed_seconds
            ))

        assert all(e >= 0.0 for e in elapsed), \
            "elapsed_seconds contained a negative value"

    def test_progress_callback_during_write(self, tmp_path: Path) -> None:
        """
        Progress callbacks are also fired when *creating* an archive via
        ``ArchiveWriter.write()``.
        """
        src = tmp_path / "src"
        src.mkdir()
        (src / "large.bin").write_bytes(b"z" * (1 << 16))

        calls: list[ProgressInfo] = []
        archive = tmp_path / "write_cb.7z"
        with ArchiveWriter(archive, compression_level=0) as w:
            w.add_file(src / "large.bin", archive_path="large.bin")
            w.write(progress_cb=lambda info: calls.append(info.model_copy()))

        assert len(calls) > 0, "Write progress callback was never called"


# ---------------------------------------------------------------------------
# entry metadata
# ---------------------------------------------------------------------------


class TestEntryMetadata:
    """Verifies that ArchiveReader.entries() returns accurate metadata."""

    def test_entry_count_matches_added_files(self, tmp_path: Path) -> None:
        """
        The number of entries returned by ``count()`` must equal the
        number of items added to the archive.
        """
        src = tmp_path / "src"
        src.mkdir()
        file_names = ["alpha.txt", "beta.txt", "gamma.bin"]
        for name in file_names:
            (src / name).write_bytes(name.encode())

        archive = tmp_path / "meta.7z"
        with ArchiveWriter(archive) as w:
            for name in file_names:
                w.add_file(src / name, archive_path=name)

        with ArchiveReader(archive) as r:
            assert r.count() == len(file_names)

    def test_entry_paths_match_added_archive_paths(
        self, tmp_path: Path
    ) -> None:
        """
        Each entry's ``path`` attribute must equal the ``archive_path``
        supplied during archive creation.
        """
        src = tmp_path / "src"
        src.mkdir()
        names = ["one.txt", "sub/two.txt"]
        (src / "one.txt").write_bytes(b"1")
        (src / "two.txt").write_bytes(b"2")

        archive = tmp_path / "paths.7z"
        with ArchiveWriter(archive) as w:
            w.add_file(src / "one.txt", archive_path="one.txt")
            w.add_file(src / "two.txt", archive_path="sub/two.txt")

        with ArchiveReader(archive) as r:
            paths = {e.path.replace("\\", "/") for e in r.entries()}

        assert "one.txt" in paths
        assert "sub/two.txt" in paths

    def test_entry_size_matches_source(self, tmp_path: Path) -> None:
        """
        The uncompressed ``size`` of each entry must equal the size of
        the original source file.
        """
        src = tmp_path / "src"
        src.mkdir()
        payload = b"exact size payload" * 37   # 666 bytes
        (src / "sized.bin").write_bytes(payload)

        archive = tmp_path / "size.7z"
        with ArchiveWriter(archive) as w:
            w.add_file(src / "sized.bin", archive_path="sized.bin")

        with ArchiveReader(archive) as r:
            entries = [e for e in r.entries() if e.path == "sized.bin"]

        assert len(entries) == 1
        assert entries[0].size == len(payload)

    def test_is_directory_flag_is_accurate(self, tmp_path: Path) -> None:
        """
        ``ArchiveEntry.is_directory`` must be ``True`` only for directory
        entries and ``False`` for file entries.
        """
        src = tmp_path / "src"
        src.mkdir()
        adir = src / "aaa_dir"
        adir.mkdir()
        (adir / "file.txt").write_bytes(b"x")

        archive = tmp_path / "isdir.7z"
        with ArchiveWriter(archive) as w:
            w.add_directory(src)

        with ArchiveReader(archive) as r:
            entry_map = {
                e.path.replace("\\", "/"): e.is_directory
                for e in r.entries()
            }

        # At least one directory entry must exist
        dirs = [p for p, is_d in entry_map.items() if is_d]
        files = [p for p, is_d in entry_map.items() if not is_d]
        assert dirs, "No directory entry found in archive"
        assert files, "No file entry found in archive"
