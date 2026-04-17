# 7z.py

[![PyPI - Version](https://img.shields.io/pypi/v/7z.py)](https://pypi.org/project/7z.py/) [![PyPI - Python Version](https://img.shields.io/pypi/pyversions/7z.py)](https://pypi.org/project/7z.py/) [![PyPI - License](https://img.shields.io/pypi/l/7z.py)](LICENSE) [![Tests](https://github.com/Modding-Forge/7z.py/actions/workflows/ci.yml/badge.svg)](https://github.com/Modding-Forge/7z.py/actions/workflows/ci.yml)

Python ctypes interface for **7z.dll** (the 7-Zip archive library).Supports reading, extracting, and creating 7z archives with optional
password protection and real-time progress callbacks - all via the native
7-Zip COM interface, no subprocess required.

> **Windows only** - requires a 7z.dll for the matching architecture.
> Bundles 7z.dll for x64, x86, and ARM64.

---

## Installation

```bash
uv add 7z.py
```

or

```bash
pip install 7z.py
```

Python 3.12+ and Windows are required.

---

## Quick start

### List entries

```python
from py7z import ArchiveReader

with ArchiveReader("archive.7z") as reader:
    for entry in reader.list_entries():
        print(entry.path, entry.size)
```

### Extract all

```python
from pathlib import Path
from py7z import ArchiveReader

with ArchiveReader("archive.7z") as reader:
    reader.extract_all(output_dir=Path("out/"))
```

### Create an archive

```python
from pathlib import Path
from py7z import ArchiveWriter, ArchiveEntryInput

entries = [ArchiveEntryInput.from_path(p) for p in Path("src/").rglob("*")]

with ArchiveWriter("archive.7z") as writer:
    writer.write(entries)
```

### Progress callbacks

```python
from py7z import ArchiveWriter, ArchiveEntryInput, ProgressInfo

def on_progress(info: ProgressInfo) -> None:
    print(info.summary)

entries = [ArchiveEntryInput.from_path(p) for p in Path("src/").rglob("*")]

with ArchiveWriter("archive.7z") as writer:
    writer.write(entries, progress_cb=on_progress)
```

`ProgressInfo.summary` produces output like:

```
 42.3%  9.5 MB/s  elapsed 0:05  rem 0:02  [3/5 files]  'src/foo.py'
```

### Password protection

```python
# Create
with ArchiveWriter("secret.7z", password="hunter2") as writer:
    writer.write(entries)

# Extract
with ArchiveReader("secret.7z", password="hunter2") as reader:
    reader.extract_all(output_dir=Path("out/"))
```

---

## Platform support

| Wheel tag     | Architecture |
| ------------- | ------------ |
| `win_amd64` | x64 (64-bit) |
| `win32`     | x86 (32-bit) |
| `win_arm64` | ARM64        |

---

## License

MIT - see [LICENSE](LICENSE).
Bundles **7z.dll**
(LGPL-2.1-or-later).

---

## About Modding Forge

7z.py was built for the Python tooling powering **[Modding Forge](https://moddingforge.com)** -
a community dedicated to Skyrim modding.
If you enjoy modding or want to connect with other modders, come say hi!
