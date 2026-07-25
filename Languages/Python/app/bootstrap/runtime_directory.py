from __future__ import annotations

import os
import stat
import tempfile


def create_private_runtime_directory(
    *, prefix: str = "trading-bot-qt-runtime-"
) -> tempfile.TemporaryDirectory[str]:
    """Create a process-lifetime runtime directory without a predictable path."""
    directory = tempfile.TemporaryDirectory(prefix=prefix)
    try:
        os.chmod(directory.name, stat.S_IRWXU)
        if os.name == "posix":
            metadata = os.stat(directory.name, follow_symlinks=False)
            if not stat.S_ISDIR(metadata.st_mode):
                raise OSError("runtime path is not a directory")
            if stat.S_IMODE(metadata.st_mode) != stat.S_IRWXU:
                raise OSError("runtime directory permissions are not owner-only")
    except BaseException:
        directory.cleanup()
        raise
    return directory
