# Known Environment Profile

The initial UAV-CI release supports one execution environment:

`px4-gz-x500-v1`

## Pinned configuration

The profile records:

- PX4 commit `e4a0bc726e20a6796c08786e3199771c5c914499`
- PX4 description `v1.18.0-beta1-416-ge4a0bc726e`
- Gazebo-models commit `bb0b9cf974acf4f1bcb5f5fcf80b88841562dea9`
- Gazebo Sim `8.15.0`
- PX4 build target `px4_sitl`
- simulator target `gz_x500`
- Gazebo world `default`
- vehicle model `x500`
- MAVSDK address `udp://:14540`

The PX4 repository and its submodules must be clean before a run begins. A commit hash does not completely identify an environment when tracked files have local modifications.

## Wind capability

The manual wind defect lab required this X500 SDF setting:

```xml
<enable_wind>true</enable_wind>
```

The modification is preserved as:

`environments/patches/x500-enable-wind.patch`

UAV-CI must not apply this patch directly to the shared PX4 checkout. The future wind adapter will copy the required model into the run workspace, verify the patch digest, and apply it to that isolated copy.

A wind scenario must still prove that wind was activated before
evaluating vehicle response.