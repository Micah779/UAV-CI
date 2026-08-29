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

class ComparisonOperator(StrEnum):
    EQUAL = "equal"
    NOT_EQUAL = "not_equal"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    EXISTS = "exists"

class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"