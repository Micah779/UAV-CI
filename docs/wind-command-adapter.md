# Wind command adapter

## Scope

The initial adapter targets one UAV-CI-owned Gazebo session using the `default` world. It publishes `gz.msgs.Wind` messagesto `/world/default/wind`.

It is not yet connected to mission execution. The runtime will eventually call it only after airborne state has been proven.

## Coordinate convention

Velocity is expressed in Gazebo world coordinates, in meters per second.

The scenario angle is measured from positive X toward positive Y:

- 0 degrees: velocity toward positive X.
- 90 degrees: velocity toward positive Y.
- 180 degrees: velocity toward negative X.
- 270 degrees: velocity toward negative Y.

This is a direction-of-travel convention, not hte meterological direction from which wind orginates.

Scenario-generated commands have zero vertical velocity.

## Command execution

Commands run without a shell and have a bounded publisher lifetime. Timeout or cancellation terminates the publisher's process group and waits for its output collection to finish.

The adapter inherits the current Gazebo transport environment and uses the loopback interface for the pinned local configuration. Concurrent unrelated sessions sharing the same world name and transport partition are outside the supported configuration.

The adapter rejects nonzero exit status and unrecognized stderr diagnostics. Only the narrowly matched informational gRPC fork diagnostic observed on the pinned installation is tolerated, and it remains in the command receipt. Gazebo CLI errors are not always represented by exit status alone. Accepting this diagnostic does not prove command delivery or wind activation.

## Receipt versus proof

A WindCommandReceipt records the arguments, process output, and host-monotonic timing of command execution.

It does not prove subscriber presence, command delivery, simulated wind velocity, or force application to the vehicle.

A timeout means command delivery is unknown, not that the command definitely did not take effect.

Gazebo WindEffects' wind_info service exposes the current commanded seed state. That readback alone is not sufficient evidence for the wind_reached_vehicle assertion.

Independent activation evidence must exist before response
assertions are evaluated.

## Disable semantics

The disable operation requests zero seed velocity with
enable_wind set to false.

This does not prove restoration, undo vehicle motion, or restore an arbitrary previous wind configuration. The owning controller must perform cleanup even when command delivery is uncertain.

## Reference

[Gazebo 8 WindEffects implementation](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/wind_effects/WindEffects.cc)