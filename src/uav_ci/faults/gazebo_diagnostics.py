# narrow diagnostic policy for the pinned Gazebo CLI installation

import re

GRPC_FORK_DIAGNOSTIC = re.compile(
    r"I[0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+\s+"
    r"[0-9]+ ev_poll_posix\.cc:[0-9]+\] "
    r"FD from fork parent still in poll list:\s*"
    r"fd\([0-9]+, generation: [0-9]+\)"
)


def has_unrecognized_stderr(stderr: str) -> bool:
    return any(
        GRPC_FORK_DIAGNOSTIC.fullmatch(line.strip()) is None
        for line in stderr.splitlines()
        if line.strip()
    )