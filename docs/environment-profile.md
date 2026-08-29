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

## Validation and identity

Environment files are parsed with PyYAML's safe loader and validated through the immutable `EnvironmentProfile` model.

Every declared patch must exist beneath the UAV-CI repository and match its declared SHA-256 digest. A missing or modified patch makes the environment invalid.

The validated profile is serialized as canonical JSON and assigned a SHA-256 environment hash. Comments, whitespace, and YAML mapping-key order do not affect this identity.

The environment hash identifies declared configuration. Runtime
preflight must separately prove that the installed PX4 revision, submodule revision, Gazebo version, and clean-worktree state match the profile.

## Runtime preflight

Loading a profile proves that its YAML and repository-owned patch files are internally valid. Preflight separately compares that declaration with the installed host environment.

Preflight is read-only and does not launch PX4 or Gazebo. It checks the PX4 revision, clean-worktree state, Gazebo-models revision, submodule cleanliness, Gazebo version, and required launch tools.

A failed environment precondition makes a run invalid. It does not represent a failure of PX4 vehicle behavior.