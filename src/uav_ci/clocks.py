# shared UAV-CI clock functions

from datetime import datetime, timezone


def utc_now() -> datetime:
    # return the current timezone-aware UTC time

    return datetime.now(timezone.utc)