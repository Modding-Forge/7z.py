"""
Copyright (c) Modding Forge
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

_PLAT_TO_ARCH: dict[str, str] = {
    "win_amd64": "x64",
    "win32": "x32",
    "win_arm64": "arm64",
}


class CustomBuildHook(BuildHookInterface):
    """
    Hatchling build hook that injects the correct 7z.dll into the wheel.

    Reads the ``WHEEL_PLAT`` environment variable to determine the target
    platform (``win_amd64`` | ``win32`` | ``win_arm64``) and overrides the
    wheel tag accordingly.  Only the DLL matching the target architecture is
    bundled into the wheel; all other architecture directories are excluded.
    """

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """
        Sets the wheel platform tag and bundles the correct 7z.dll.

        Args:
            version (str): The current project version string.
            build_data (dict[str, Any]): Mutable build metadata provided
                by hatchling.
        """

        plat: str = os.environ.get("WHEEL_PLAT", "win_amd64")
        arch: str = _PLAT_TO_ARCH.get(plat, "x64")

        build_data["pure_python"] = False
        build_data["tag"] = f"py3-none-{plat}"

        dll_source: Path = Path("res") / arch / "7z.dll"
        dll_dest: str = f"mf_7z/res/{arch}/7z.dll"
        build_data["force_include"][str(dll_source)] = dll_dest
