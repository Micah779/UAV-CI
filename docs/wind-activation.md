# Wind activation assessment

The evaluator is a pure function over trusted observer records from one UAV-CI-owned run. It does not publish commands, read artifacts, check file hashes, or control the vehicle. The caller must supply records and command
timestamps from the same managed simulator session.

## Initial policy

A pre-command baseline must be unpaused, have wind enabled on the target link, and finish no more than one host second before command publication starts. Actual wind and requested seed must both be calm: their magnitudes must not exceed the smaller of 0.000001 m/s and one tenth of the configured activation threshold.

Activation requires two consecutive post-command observations with:

- The same world, wind, model, and link entity IDs as the baseline.
- Strictly advancing Gazebo simulation time and iteration count.
- An unpaused world and wind enabled on the target link.
- Actual horizontal wind speed at or above the configured threshold.
- Actual total speed no greater than 105% of the commanded speed.
- Actual direction within 10 degrees of the requested world-frame direction.
- Actual vertical speed no greater than 0.1 m/s in magnitude.
- A requested seed matching the command, allowing textual rounding.

These tolerances are UAV-CI's initial evaluator policy, not Gazebo defaults or newly configurable scenario fields. The seed is only a consistency check; it can never prove activation without matching actual wind.

## Ordering and deadlines

The activation budget begins at command publication start, not completion. Each post-command state request must start after publication completes and finish within the activation budget. Requests cannot overlap or arrive out of order. Records are never sorted to manufacture a passing sequence.

Host-monotonic time controls request ordering and deadlines. Gazebo time and iterations establish simulator progression. Different clock domains are never directly compared.

Valid advancing samples below the threshold or outside the requested wind criteria reset the consecutive-sample count, allowing normal wind ramp-up. Invalid timing, changed identities, paused state, or a wind-disabled link
reject the assessment. Malformed input raises ValueError.

## Meaning and limits

A successful assessment retains the baseline and the first qualifying pair. It establishes a bounded calm-to-wind simulator-field transition under the pinned uniform-wind, single-owner environment contract.

It does not directly measure applied force, global wind enable state, airborne triggering, sustained exposure, or vehicle behavior. Samples after the first qualifying pair are not evaluated for continued exposure. It is not a final assertion or run classification.

An unsuccessful assessment provides a reason, never a vehicle behavior failure. Raw observations remain in the observer artifacts. A subsequent controller must persist the assessment, map it to activation evidence, and prevent response evaluation when activation is unproven.