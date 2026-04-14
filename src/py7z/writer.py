"""
Copyright (c) Modding Forge
"""

from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Optional

from ._callbacks import ProgressCallback, UpdateCallback
from ._com import COMPtr, HRESULT_T, PVOID, com_method, check_hr
from ._dll import create_out_archive
from ._guids import FORMAT_EXTENSION_MAP, GUID, CLSID_7z
from ._streams import FileOutStream
from .entry import ArchiveEntryInput
from .exceptions import ArchiveFormatError

# ---------------------------------------------------------------------------
# IOutArchive vtable slot indices
# ---------------------------------------------------------------------------

_VTBL_UPDATE_ITEMS: int = 3
_VTBL_GET_FILE_TIME_TYPE: int = 4

_UPDATE_ITEMS_FUNC = com_method(
    HRESULT_T,
    PVOID,                 # this
    ctypes.c_void_p,        # ISequentialOutStream*
    ctypes.c_uint32,        # numItems
    ctypes.c_void_p,        # IArchiveUpdateCallback*
)
_GET_FILE_TIME_TYPE_FUNC = com_method(
    HRESULT_T, PVOID, ctypes.POINTER(ctypes.c_uint32)
)

# ISetProperties vtable slot (index 3 relative to ISetProperties vtable)
_SET_PROPERTIES_VTBL: int = 3
_SET_PROPERTIES_FUNC = com_method(
    HRESULT_T,
    PVOID,
    ctypes.POINTER(ctypes.c_wchar_p),  # names
    ctypes.c_void_p,                    # values (PROPVARIANT*)
    ctypes.c_uint32,                    # numProps
)

# ISetProperties interface ID
from ._guids import IID_ISetProperties


class ArchiveWriter:
    """
    High-level wrapper around ``IOutArchive`` for creating 7-Zip archives.

    Usage::

        with ArchiveWriter(Path("out.7z")) as writer:
            writer.add_file(Path("readme.txt"))
            writer.add_directory(Path("src/"), base=Path("."))
            writer.write()
    """

    _output_path: Path
    _format_clsid: GUID
    _dll_path: Optional[Path]
    _entries: list[ArchiveEntryInput]
    _password: Optional[str]
    _compression_level: int
    _solid: bool
    _written: bool

    def __init__(
        self,
        output_path: Path,
        format_clsid: Optional[GUID] = None,
        password: Optional[str] = None,
        compression_level: int = 5,
        solid: bool = True,
        dll_path: Optional[Path] = None,
    ) -> None:
        """
        Configures the archive writer.

        Args:
            output_path (Path): Destination ``.7z`` (or other format) path.
            format_clsid (Optional[GUID]): Override the format CLSID.
                When ``None`` the CLSID is derived from the file extension,
                and defaults to 7z when unknown.
            password (Optional[str]): Encryption password.
            compression_level (int): Compression level 0-9 (default 5).
            solid (bool): Enable solid compression (default ``True``).
            dll_path (Optional[Path]): Custom path to 7z.dll.
        """

        self._output_path = output_path
        self._dll_path = dll_path
        self._entries = []
        self._password = password
        self._compression_level = max(0, min(9, compression_level))
        self._solid = solid
        self._written = False

        if format_clsid is not None:
            self._format_clsid = format_clsid
        else:
            ext: str = output_path.suffix.lower()
            self._format_clsid = FORMAT_EXTENSION_MAP.get(ext, CLSID_7z)

    def __enter__(self) -> "ArchiveWriter":
        """
        Returns *self* when entering a ``with`` block.

        Returns:
            ArchiveWriter: This instance.
        """

        return self

    def __exit__(self, *_: object) -> None:
        """
        Flushes the archive when leaving a ``with`` block.

        Does nothing if :meth:`write` was already called explicitly.
        """

        if not self._written:
            self.write()

    def add_file(
        self,
        path: Path,
        archive_path: Optional[str] = None,
    ) -> None:
        """
        Adds a single file to the pending entry list.

        Args:
            path (Path): Source file path.
            archive_path (Optional[str]): Override the path stored in the
                archive.  Defaults to the file name only.

        Raises:
            FileNotFoundError: If *path* does not exist.
        """

        if not path.exists():
            raise FileNotFoundError(f"Source file not found: '{path}'")
        entry = ArchiveEntryInput.from_path(path)
        if archive_path is not None:
            entry = entry.model_copy(update={"archive_path": archive_path})
        self._entries.append(entry)

    def add_directory(
        self,
        directory: Path,
        base: Optional[Path] = None,
        recursive: bool = True,
    ) -> None:
        """
        Adds all files inside *directory* to the pending entry list.

        Directory entries are also added so that empty subdirectories
        are preserved.

        Args:
            directory (Path): Root directory to add.
            base (Optional[Path]): Base for relative path calculation.
                Defaults to *directory*.
            recursive (bool): Whether to recurse into subdirectories.

        Raises:
            NotADirectoryError: If *directory* is not an existing directory.
        """

        if not directory.is_dir():
            raise NotADirectoryError(
                f"Not a directory: '{directory}'"
            )
        effective_base: Path = base if base is not None else directory.parent
        glob_pattern: str = "**/*" if recursive else "*"
        for item in sorted(directory.glob(glob_pattern)):
            self._entries.append(
                ArchiveEntryInput.from_path(item, effective_base)
            )

    def write(
        self,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> None:
        """
        Creates the archive and writes all pending entries to disk.

        The output file and any missing parent directories are created
        automatically.

        Args:
            progress_cb (Optional[ProgressCallback]): Optional progress
                callback ``(completed, total) -> None``.

        Raises:
            HResultError: If a COM operation fails.
            DllLoadError: If 7z.dll cannot be loaded.
        """

        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        archive: COMPtr = create_out_archive(
            self._format_clsid, self._dll_path
        )
        self._apply_properties(archive)

        out_stream = FileOutStream(self._output_path)
        cb = UpdateCallback(
            entries=self._entries,
            progress_cb=progress_cb,
            password=self._password,
        )
        update_fn = _UPDATE_ITEMS_FUNC(
            archive._vtable[_VTBL_UPDATE_ITEMS]
        )
        hr: int = update_fn(
            archive.raw,
            out_stream.as_void_p,
            ctypes.c_uint32(len(self._entries)),
            cb.as_void_p,
        )
        out_stream.close()
        check_hr(hr, "IOutArchive::UpdateItems")
        self._written = True

    def _apply_properties(self, archive: COMPtr) -> None:
        """
        Calls ``ISetProperties::SetProperties`` to configure compression.

        Falls back silently if the interface is not supported by the handler.

        Args:
            archive (COMPtr): The ``IOutArchive`` COM pointer.
        """

        from ._propvariant import PROPVARIANT, VT_UI4

        try:
            set_props = archive.query_interface(IID_ISetProperties)
        except Exception:
            return

        names: list[str] = ["x", "s"]
        vals: list[PROPVARIANT] = []

        pv_level = PROPVARIANT()
        pv_level.vt = VT_UI4
        pv_level._data.ulVal = self._compression_level
        vals.append(pv_level)

        pv_solid = PROPVARIANT()
        pv_solid.vt = VT_UI4
        pv_solid._data.ulVal = 1 if self._solid else 0
        vals.append(pv_solid)

        c_names = (ctypes.c_wchar_p * len(names))(
            *[ctypes.c_wchar_p(n) for n in names]
        )
        PropVariantArray = PROPVARIANT * len(vals)
        c_vals = PropVariantArray(*vals)

        set_fn = _SET_PROPERTIES_FUNC(
            set_props._vtable[_SET_PROPERTIES_VTBL]
        )
        set_fn(
            set_props.raw,
            c_names,
            c_vals,
            ctypes.c_uint32(len(names)),
        )
