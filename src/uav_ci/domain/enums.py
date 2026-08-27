'''
Defines UAV-CI's shared vocabulary. The System will use predefined enums for
results, assertions, evidence, and timestamps.

ResultStatus : describes the final result of the entire test run
AssertionLayer : describes what an individual assertion is trying to prove
CheckOutcome : describes the result of one assertion
EvidenceSource : records where the proof came from
ClockDomain : records what a timestamp means

ideal classifier enforcement order:

Harness/infra failure                -> ERROR
Unsupported pre-launch env           -> SKIPPED
Missing precondition or activation   -> INVALID
Valid stimulus, failed response      -> FAIL
Valid stimulus, all chekcs passed    -> PASS
'''

from enum import StrEnum

class ResultStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INVALID = "invalid"
    ERROR = "error"
    SKIPPED = "skipped"

class AssertionLayer(StrEnum):
    PRECONDITION = "precondition"
    ACTIVATION = "activation"
    RESPONSE = "response"
    OUTCOME = "outcome"

class CheckOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    NOT_EVALUATED = "not_evaluated"

class EvidenceSource(StrEnum):
    HARNESS = "harness"
    COMMAND = "command"
    SIMULATOR = "simulator"
    TELEMETRY = "telemetry"
    ULOG = "ulog"

class ClockDomain(StrEnum):
    UTC = "utc"
    HOST_MONOTONIC = "host_monotonic"
    PX4_BOOT = "px4_boot"