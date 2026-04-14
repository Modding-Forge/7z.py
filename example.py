"""
Copyright (c) Modding Forge
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from py7z import ArchiveReader, ArchiveWriter, ProgressInfo
from py7z.entry import ArchiveEntryInput
from py7z.exceptions import (
    ExtractionError,
    PasswordRequiredError,
    WrongPasswordError,
)

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s  %(message)s")
log: logging.Logger = logging.getLogger("example")

ARCHIVE_PATH: Path = Path("res/example.7z")
OUTPUT_DIR: Path = Path("example_output/extracted")
NEW_ARCHIVE_PATH: Path = Path("example_output/created.7z")
SRC_DIR: Path = Path("src")

LARGE_SRC_DIR: Path = Path("example_output/large_src")
LARGE_ARCHIVE_PATH: Path = Path("example_output/large.7z")
LARGE_EXTRACT_DIR: Path = Path("example_output/large_extracted")


def demo_list(archive_path: Path) -> None:
    """
    Lists all entries in an archive and prints their metadata.

    Args:
        archive_path (Path): Path to the archive to inspect.
    """

    log.info("=== Listing entries in '%s' ===", archive_path)
    with ArchiveReader(archive_path) as reader:
        log.info("Total items: %d", reader.count())
        for entry in reader.entries():
            kind: str = "<DIR>" if entry.is_directory else "     "
            enc: str = "[ENC]" if entry.encrypted else "     "
            log.info(
                "  %s %s  %10d bytes  %s",
                kind,
                enc,
                entry.size,
                entry.path,
            )


def demo_extract_all(archive_path: Path, output_dir: Path) -> None:
    """
    Extracts all entries of an archive into *output_dir*.

    Args:
        archive_path (Path): Path to the archive to extract.
        output_dir (Path): Destination directory.
    """

    log.info("=== Extracting all to '%s' ===", output_dir)

    def on_progress(info: ProgressInfo) -> None:
        """Reports extraction progress to the log."""

        log.debug("  %s", info.summary)

    try:
        with ArchiveReader(archive_path) as reader:
            reader.extract_all(output_dir, progress_cb=on_progress)
        log.info("Extraction complete.")
    except WrongPasswordError:
        log.error("Wrong or missing password for '%s'.", archive_path)
    except ExtractionError as exc:
        log.error("Extraction failed: %s", exc)


def demo_extract_single(archive_path: Path) -> None:
    """
    Extracts the first non-directory entry and prints its content.

    Args:
        archive_path (Path): Path to the archive.
    """

    log.info("=== Extracting single entry ===")
    with ArchiveReader(archive_path) as reader:
        for entry in reader.entries():
            if entry.is_directory:
                continue
            log.info("  Reading entry: '%s'", entry.path)
            data: bytes = reader.extract_entry(entry.index)
            log.info("  Size on disk: %d bytes", len(data))
            # Print first 200 chars for text files
            if entry.suffix in (".txt", ".py", ".md", ".ini", ".cfg"):
                preview: str = data[:200].decode("utf-8", errors="replace")
                log.info("  Preview:\n%s", preview)
            break


def demo_extract_with_password(
    archive_path: Path, output_dir: Path, password: str
) -> None:
    """
    Extracts a password-protected archive.

    Args:
        archive_path (Path): Path to the encrypted archive.
        output_dir (Path): Destination directory.
        password (str): Decryption password.
    """

    log.info("=== Extracting with password ===")
    with ArchiveReader(archive_path, password=password) as reader:
        reader.extract_all(output_dir)
    log.info("Extraction complete.")


def demo_create(output_path: Path, source_dir: Path) -> None:
    """
    Creates a new ``.7z`` archive from all files in *source_dir*.

    Args:
        output_path (Path): Destination archive path.
        source_dir (Path): Directory whose contents to compress.
    """

    log.info("=== Creating archive '%s' from '%s' ===", output_path, source_dir)

    def on_progress(info: ProgressInfo) -> None:
        """Reports compression progress to the log."""

        log.debug("  %s", info.summary)

    with ArchiveWriter(
        output_path,
        compression_level=5,
        solid=True,
    ) as writer:
        writer.add_directory(source_dir, base=source_dir.parent)
        writer.write(progress_cb=on_progress)

    log.info(
        "Archive created: %.1f KB",
        output_path.stat().st_size / 1024,
    )


def demo_create_with_password(
    output_path: Path, files: list[Path]
) -> None:
    """
    Creates an encrypted ``.7z`` archive.

    Args:
        output_path (Path): Destination archive path.
        files (list[Path]): Individual files to include.
    """

    log.info("=== Creating encrypted archive '%s' ===", output_path)
    with ArchiveWriter(output_path, password="secret123", compression_level=9) as w:
        for f in files:
            if f.exists():
                w.add_file(f)
    log.info("Encrypted archive created.")


def demo_extract_to_disk(archive_path: Path, output_dir: Path) -> None:
    """
    Extracts a single entry both as bytes and to disk.

    This demonstrates passing *output_dir* to
    :meth:`~py7z.ArchiveReader.extract_entry`.

    Args:
        archive_path (Path): Path to the archive.
        output_dir (Path): Directory for the extracted file.
    """

    log.info("=== Extracting single entry to disk ===" )
    with ArchiveReader(archive_path) as reader:
        for entry in reader.entries():
            if entry.is_directory:
                continue
            log.info("  Extracting '%s' to '%s'", entry.path, output_dir)
            data: bytes = reader.extract_entry(
                entry.index, output_dir=output_dir
            )
            dest: Path = output_dir / entry.path.replace("\\", "/")
            log.info(
                "  Written %d bytes → '%s'  (exists: %s)",
                len(data),
                dest,
                dest.exists(),
            )
            break


def demo_add_with_custom_path(output_path: Path) -> None:
    """
    Creates an archive with files stored under custom archive paths.

    This demonstrates using :class:`~py7z.ArchiveEntryInput` directly
    and overriding the *archive_path* stored inside the archive.

    Args:
        output_path (Path): Destination archive path.
    """

    log.info("=== Creating archive with custom entry paths ===" )
    with ArchiveWriter(output_path) as writer:
        for src in [Path("pyproject.toml"), Path("example.py")]:
            if src.exists():
                entry = ArchiveEntryInput.from_path(src)
                entry = entry.model_copy(
                    update={"archive_path": f"custom/{src.name}"}
                )
                writer._entries.append(entry)
        writer.write()
    log.info(
        "Custom-path archive: %.1f KB",
        output_path.stat().st_size / 1024,
    )


def demo_wrong_password(archive_path: Path) -> None:
    """
    Demonstrates :exc:`~py7z.exceptions.WrongPasswordError` and
    :exc:`~py7z.exceptions.PasswordRequiredError` handling.

    Args:
        archive_path (Path): Path to a password-protected archive.
    """

    log.info("=== Wrong-password error handling ===")
    # No password at all → 7-Zip returns UNSUPPORTED_METHOD or
    # WrongPasswordError depending on the archive type.
    try:
        with ArchiveReader(archive_path) as reader:
            reader.extract_all(Path("example_output/wrong_pw_out"))
    except (WrongPasswordError, PasswordRequiredError, ExtractionError) as exc:
        log.info("  Expected error (no password): %s", type(exc).__name__)

    # Wrong password
    try:
        with ArchiveReader(archive_path, password="wrong") as reader:
            reader.extract_all(Path("example_output/wrong_pw_out"))
    except (WrongPasswordError, ExtractionError) as exc:
        log.info("  Expected error (wrong password): %s", type(exc).__name__)


def demo_archive_properties(archive_path: Path) -> None:
    """
    Reads and logs global archive properties (type, solid, etc.).

    Args:
        archive_path (Path): Path to the archive to inspect.
    """

    from py7z.entry import KPID_TYPE, KPID_SOLID, KPID_ENCRYPTED

    log.info("=== Archive properties of '%s' ===", archive_path)
    with ArchiveReader(archive_path) as reader:
        archive_type: object = reader.get_archive_property(KPID_TYPE)
        solid: object = reader.get_archive_property(KPID_SOLID)
        encrypted: object = reader.get_archive_property(KPID_ENCRYPTED)
        log.info("  Type     : %s", archive_type)
        log.info("  Solid    : %s", solid)
        log.info("  Encrypted: %s", encrypted)


def _generate_large_files(
    target_dir: Path,
    total_bytes: int,
) -> None:
    """
    Generates incompressible random binary files in *target_dir*
    totalling approximately *total_bytes* bytes.

    Existing files with the correct size are reused to avoid
    redundant I/O on repeated runs.

    Args:
        target_dir (Path): Directory to place generated files.
        total_bytes (int): Approximate total size in bytes.
    """

    target_dir.mkdir(parents=True, exist_ok=True)
    write_chunk: int = 8 * 1024 * 1024   # 8 MiB per write call
    file_size: int = 1024 ** 3           # 1 GiB per file
    num_files: int = max(1, (total_bytes + file_size - 1) // file_size)
    for i in range(num_files):
        path: Path = target_dir / f"data_{i:02d}.bin"
        if path.exists() and path.stat().st_size == file_size:
            log.info(
                "  Reusing '%s'  (%d MiB)",
                path,
                file_size // 1024 ** 2,
            )
            continue
        log.info(
            "  Generating '%s'  (%d MiB)...",
            path,
            file_size // 1024 ** 2,
        )
        t0: float = time.perf_counter()
        with path.open("wb") as fh:
            remaining: int = file_size
            while remaining > 0:
                block: int = min(write_chunk, remaining)
                fh.write(os.urandom(block))
                remaining -= block
        elapsed: float = time.perf_counter() - t0
        speed: float = (
            (file_size / 1024 ** 2) / max(elapsed, 1e-6)
        )
        log.info(
            "  \u2192 %d MiB written in %.1f s  (%.0f MiB/s)",
            file_size // 1024 ** 2,
            elapsed,
            speed,
        )


def demo_large_run(
    src_dir: Path,
    archive_path: Path,
    extract_dir: Path,
    total_bytes: int = 5 * 1024 ** 3,
) -> None:
    """
    Second run: all archive operations on a large synthetic dataset.

    Generates approximately *total_bytes* of incompressible random
    binary data, then exercises create (store mode), list,
    extract-all, and archive-property reads - all with live progress
    reporting via :class:`~py7z.ProgressInfo`.

    Store mode (``compression_level=0``) is used so that the
    operation is I/O-bound rather than CPU-bound and the progress
    callbacks fire at a useful rate regardless of codec speed.

    Note: single-entry in-memory extraction
    (:meth:`~py7z.ArchiveReader.extract_entry`) is omitted because
    it buffers the entire entry into RAM, which is impractical for
    GiB-sized files.

    Args:
        src_dir (Path): Directory for synthetic source files.
        archive_path (Path): Destination archive path.
        extract_dir (Path): Directory for extracted output.
        total_bytes (int): Total synthetic input size in bytes.
    """

    gb: float = total_bytes / 1024 ** 3
    log.info("=== LARGE-ARCHIVE RUN  (%.1f GiB) ===", gb)

    log.info("--- Generating synthetic source files ---")
    _generate_large_files(src_dir, total_bytes)

    log.info("--- Creating archive (store, no compression) ---")

    def on_compress(info: ProgressInfo) -> None:
        """Logs compression progress for the large-archive run."""

        log.debug("  [compress] %s", info.summary)

    archive_path.unlink(missing_ok=True)
    with ArchiveWriter(
        archive_path,
        compression_level=0,
        solid=False,
    ) as writer:
        writer.add_directory(src_dir, base=src_dir.parent)
        writer.write(progress_cb=on_compress)
    log.info(
        "  Archive written: %.1f MiB",
        archive_path.stat().st_size / 1024 ** 2,
    )

    log.info("--- Listing archive entries ---")
    demo_list(archive_path)

    log.info("--- Extracting all entries ---")

    def on_extract(info: ProgressInfo) -> None:
        """Logs extraction progress for the large-archive run."""

        log.debug("  [extract] %s", info.summary)

    try:
        with ArchiveReader(archive_path) as reader:
            reader.extract_all(extract_dir, progress_cb=on_extract)
        log.info("  Extraction complete.")
    except ExtractionError as exc:
        log.error("  Extraction failed: %s", exc)

    log.info("--- Archive-level properties ---")
    demo_archive_properties(archive_path)


if __name__ == "__main__":
    # --- Create a test archive from the package source ---
    demo_create(NEW_ARCHIVE_PATH, SRC_DIR)

    # --- List the newly created archive ---
    demo_list(NEW_ARCHIVE_PATH)

    # --- Extract all entries ---
    demo_extract_all(NEW_ARCHIVE_PATH, OUTPUT_DIR)

    # --- Extract a single entry (bytes only) ---
    demo_extract_single(NEW_ARCHIVE_PATH)

    # --- Extract a single entry to disk ---
    demo_extract_to_disk(NEW_ARCHIVE_PATH, Path("res/single_out"))

    # --- Read archive-level properties ---
    demo_archive_properties(NEW_ARCHIVE_PATH)

    # --- Custom archive paths via ArchiveEntryInput ---
    demo_add_with_custom_path(Path("example_output/custom_paths.7z"))

    # --- Encrypted archive round-trip ---
    encrypted_path = Path("example_output/encrypted.7z")
    demo_create_with_password(
        encrypted_path,
        [Path("pyproject.toml"), Path("example.py")],
    )
    demo_extract_with_password(
        encrypted_path,
        Path("example_output/encrypted_out"),
        password="secret123",
    )

    # --- Wrong-password error handling ---
    demo_wrong_password(encrypted_path)

    # --- Second run: all operations on large (≈5 GiB) synthetic archives ---
    demo_large_run(
        LARGE_SRC_DIR,
        LARGE_ARCHIVE_PATH,
        LARGE_EXTRACT_DIR,
    )
