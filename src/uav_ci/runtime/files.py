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

def publish_file_exclusively(
    source: Path,
    target: Path,
    *,
    chunk_size: int = 1024 * 1024,
) -> None:
    # atomically copy a file without overwriting

    if chunk_size <= 0:
        raise ValueError(
            "chunk_size must be positive"
        )

    if not source.is_file():
        raise FileNotFoundError(
            f"source file does not exist: {source}"
        )

    with source.open("rb") as source_file:
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
                while True:
                    chunk = source_file.read(
                        chunk_size
                    )

                    if not chunk:
                        break

                    temporary_file.write(chunk)

                temporary_file.flush()
                os.fsync(
                    temporary_file.fileno()
                )

            os.link(temporary_path, target)
        finally:
            temporary_path.unlink(
                missing_ok=True
            )