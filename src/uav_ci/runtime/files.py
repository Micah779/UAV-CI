# atomic, non-overwriting runtime file publication

import os
from pathlib import Path
from tempfile import mkstemp


def publish_bytes_exclusively(
    target: Path,
    contents: bytes,
) -> None:
    # atomically publish bytes without overwriting

    file_descriptor, temporary_name = mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(
            file_descriptor,
            mode="wb",
        ) as temporary_file:
            temporary_file.write(contents)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.link(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)


def publish_text_exclusively(
    target: Path,
    contents: str,
) -> None:
    # atomically publish UTF-8 text without overwriting

    publish_bytes_exclusively(
        target,
        contents.encode("utf-8"),
    )