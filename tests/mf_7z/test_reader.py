"""
Copyright (c) Modding Forge
"""

from __future__ import annotations

import io
import struct
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from mf_7z.exceptions import ArchiveOpenError


class TestArchiveReader:
    """
    Tests ``mf_7z.reader.ArchiveReader``.
    """

    def test_import(self) -> None:
        """Tests that ArchiveReader can be imported without error."""

        # given / when / then
        from mf_7z import ArchiveReader  # noqa: F401

    def test_open_nonexistent_file_raises(self, tmp_path: Path) -> None:
        """Tests that opening a missing archive raises FileNotFoundError."""

        # given
        from mf_7z import ArchiveReader

        missing: Path = tmp_path / "no_such_file.7z"

        # when / then
        with pytest.raises((FileNotFoundError, ArchiveOpenError)):
            ArchiveReader(missing)

    def test_context_manager_closes(self, tmp_path: Path) -> None:
        """Tests that __exit__ calls close() without error."""

        # given
        from mf_7z.reader import ArchiveReader

        # Patch _open so no real DLL call happens
        with patch.object(ArchiveReader, "_open", return_value=None):
            reader = ArchiveReader(tmp_path / "fake.7z")
            reader._archive = None  # already "closed"

        # when / then — must not raise
        with patch.object(ArchiveReader, "_open", return_value=None):
            with ArchiveReader(tmp_path / "fake.7z") as r:
                r._archive = None
