# Wind controller

The managed controller coordinates one wind activation attempt in one UAV-CI-owned simulator session. It implements the existing fault-controller contract and returns a prepared FaultLifecycle from its context manager.

## Ownership and ordering

Preparation creates an unused evidence/wind directory. It never reuses or overwrites an earlier controller's evidence. It does not observe or publish.

The flight owner must call activate only after observing airborne. Activate captures a fresh calm baseline immediately before attempting publication. A paused, non-calm, stale, or wind-disabled baseline prevents publication and produces an unproven activation result when prove_activation is called.

The controller does not itself verify airborne or launch/stop PX4 and Gazebo. Operations are sequential and single-owner; do not call lifecycle methods concurrently. The context must remain open for the intended wind exposure.

## Evidence and classification

Command attempts retain arguments, timing, returned output when available, receipts, and errors. Missing output is null, not a successful empty response. The observer retains state samples and observation errors separately.

The activation assessment records its stimulus, reason, decision, and run-relative links to baseline, command, observed, and supporting artifacts. Its EvidenceRef identifies a harness assessment at a host-monotonic time.
Gazebo simulation timestamps remain in the linked observations; they are not relabeled as host-monotonic time or PX4 boot time.

Insufficient observations or an observation timeout leave activation unproven. FaultLifecycle require_activation_proven keeps response evaluation
blocked. Parser failures, unexpected command errors,  missing evidence, and other infrastructure failures propagate to the flight owner. This module does not create result.json or assign the final run classification.

## Timing and diagnostics

The baseline request has a two-second budget. Wind publication has a budget of the smaller of two seconds and the scenario activation timeout. The activation window still begins at publication start; publication and any caller delay reduce the remaining observation time.

Only the narrowly matched informational gRPC fork diagnostic is accepted from command stderr. It is retained unchanged. Other nonempty diagnostics and all nonzero exit codes reject command publication.

## Cleanup

Once publication is attempted, delivery may be unknown. The context therefore attempts disable even after publication failure or cancellation. Disable requests zero seed and disabled wind with a two-second command
budget. Repeated cleanup calls do not publish another command.

Cleanup waits for its bounded attempt even when the caller is cancelled, then propagates cancellation. If cleanup fails alongside another exception,
the original exception is preserved with a cleanup-failure note. Cleanup failure on an otherwise successful path propagates as an error.

A disable receipt is not restoration proof. Cleanup artifacts explicitly set restoration_proven to false. The outer flight runner must always stop its owned simulator session, including when wind cleanup fails. Timeouts
bound asynchronous command waiting, not filesystem I/O or process-reaping latency; abrupt process termination cannot guarantee cleanup.