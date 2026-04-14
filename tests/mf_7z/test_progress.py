"""
Copyright (c) Modding Forge
"""

from __future__ import annotations

import pytest


class TestProgress:
    """
    Tests ``mf_7z.progress.ProgressInfo``.
    """

    def test_percent_calculation(self) -> None:
        """Tests that percent field stores the assigned value."""

        # given
        from mf_7z.progress import ProgressInfo

        # when
        info = ProgressInfo(
            total_bytes=1000,
            completed_bytes=250,
            percent=25.0,
        )

        # then
        assert info.percent == pytest.approx(25.0, abs=0.1)

    def test_percent_zero_when_total_unknown(self) -> None:
        """Tests that percent is 0.0 when total_bytes is 0."""

        # given
        from mf_7z.progress import ProgressInfo

        # when
        info = ProgressInfo(total_bytes=0, completed_bytes=0)

        # then
        assert info.percent == 0.0

    def test_summary_contains_percent(self) -> None:
        """Tests that summary string includes the percentage."""

        # given
        from mf_7z.progress import ProgressInfo

        info = ProgressInfo(
            total_bytes=1000,
            completed_bytes=500,
            percent=50.0,
            elapsed_seconds=1.0,
        )

        # when
        summary: str = info.summary

        # then
        assert "50" in summary
