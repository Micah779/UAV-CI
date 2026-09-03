# Wind-state observer

The observer requests full state from `/world/default/state` in the single supported local Gazebo session. It does not publish wind commands, arm the vehicle, or own simulator startup and shutdown.

## Collection bounds

Collection has a total host-monotonic budget, a per-request timeout, a polling interval, and a maximum sample count.

The total budget is not restarted after each sample. Time spent by the consumer between samples also consumes that budget.

Subprocess cleanup, synchronous decoding, and disk operations may extend wall-clock completion beyond the request timeout.

## Evidence

Each attempted request receives a numbered JSON record containing its arguments, host-monotonic timestamps, returned output, decoded observation, and any error.

The observer saves evidence before yielding a successful sample. Existing observation directories are never reused.

When the command runner raises before returning output, stdout, stderr, and returncode remain null. This means unavailable, not empty or successful.

Earlier records remain available if a later request fails.

## Diagnostics

The exact informational gRPC fork diagnostic observed on the pinned installation is tolerated for state requests and wind-command publication, and retained unchanged.

All other nonempty stderr diagnostics reject the sample. Nonzero exit codes, invalid protobuf, missing required state, and late responses also reject the sample.

The observer and publisher share the same narrow diagnostic policy. Accepting a diagnostic does not prove command delivery or wind activation.

## Assurance boundary

An observation is not activation proof.

Paused state, repeated simulation timestamps, and a wind-disabled link remain observable facts. The activation evaluator must decide whether observations are fresh and demonstrate the required stimulus.

Gazebo simulation timestamps must not be directly compared with host-monotonic timestamps or PX4 boot timestamps.