"""
Copyright (c) Modding Forge
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from py7z.exceptions import ArchiveOpenError


class TestArchiveWriter:
    """
    Tests `py7z.writer.ArchiveWriter`.
    """

    def test_import(self) -> None:
        """Tests that ArchiveWriter can be imported without error."""

        # given / when / then
        from py7z import ArchiveWriter  # noqa: F401

    def test_written_flag_prevents_double_write(
        self, tmp_path: Path
    ) -> None:
        """Tests that explicit write() inside with-block prevents re-write
        from __exit__."""

        # given
        from py7z.writer import ArchiveWriter

        out: Path = tmp_path / "test.7z"
        write_calls: list[int] = []

        def fake_write(
            entries: object = None,
            progress_cb: object = None,
        ) -> None:
            write_calls.append(1)

        writer = ArchiveWriter(out)
        writer._written = True  # simulate already written

        with patch.object(ArchiveWriter, "write", side_effect=fake_write):
            # when
            writer.__exit__(None, None, None)

        # then - write() must NOT have been called again
        assert len(write_calls) == 0
