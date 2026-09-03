# only the observed informational fork diagnostic is allowed

import asyncio

import pytest

from uav_ci.faults.gazebo_diagnostics import has_unrecognized_stderr
from uav_ci.faults.wind_command import (
    CommandOutput,
    GazeboWindCommandAdapter,
    WindCommand,
    WindCommandError,
)


DIAGNOSTIC = (
    "I0902 11:55:14.180964 6775763 ev_poll_posix.cc:593] "
    "FD from fork parent still in poll list:fd(13, generation: 1)\n"
)


@pytest.mark.parametrize("stderr,rejected", [
    ("", False), (" \n", False), (DIAGNOSTIC, False),
    (DIAGNOSTIC * 2, False),
    (DIAGNOSTIC + "Unable to create message\n", True),
    (DIAGNOSTIC.replace("I0902", "E0902"), True),
    ("unrecognized output", True),
])
def test_diagnostic_policy(stderr, rejected):
    assert has_unrecognized_stderr(stderr) is rejected


def test_nonzero_exit_is_rejected_even_with_allowed_diagnostic():
    async def runner(argv, *, timeout_s):
        return CommandOutput(1, "", DIAGNOSTIC)

    adapter = GazeboWindCommandAdapter(runner=runner)
    with pytest.raises(WindCommandError):
        asyncio.run(adapter.send(WindCommand.disabled()))