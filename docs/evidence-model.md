# Evidence Model

UAV-CI assertions must identify the evidence supporting their results.

An 'EvidenceRef' points to a specific signal, timestamp, source, and retained artifact. It does not contain the complete telemtry stream or flight log.

## Evidence sources

- `harness`: Lifecycle and process observations produced by UAV-CI
- `command`: MAVSDK or MAVLink command results
- `simulator`: State observed directly from Gazebo
- `telemetry`: Live vehicle telemetry
- `ulog`: Post-flight PX4 log evidence

## Clock domains

- `utc`: Microseconds since the Unix epoch
- `host_monotonic`: Microseconds from the host monotonic clock
- `px4_boot`: Microseconds since PX4 boot

Timestamps from different clocks domains must not be subtracted directly unless a clock correlation has been recorded.

## Artifact paths

Artifact paths are relative to the isolated run directory.

Absolute paths and parent-directory traversal are rejected so that manifests remain portable and cannot reference files outside a run.

## Example

A GNSS activation check might reference:

- Source: `telemetry`
- Signal: `vehicle_gps_position.fix_type`
- Clock: `px4_boot`
- Timestamp: `18420000`
- Artifact: `telemetry/events.jsonl`
- Description: `GNSS fix type dropped below a valid 3D fix.`