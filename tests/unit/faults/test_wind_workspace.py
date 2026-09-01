# tests for isolated Gazebo wind-model preparation

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from uav_ci.faults import (
    WindWorkspaceError,
    prepare_wind_model_workspace,
)
from uav_ci.runtime import create_run_directory


RUN_ID = UUID(
    "12345678-1234-5678-1234-567812345678"
)
STARTED_AT = datetime(
    2026,
    8,
    31,
    12,
    0,
    0,
    tzinfo=timezone.utc,
)

MODEL_SDF = """\
<sdf>
  <model>
    <link>
      <inertial>
        <inertia>
        </inertia>
      </inertial>
      <gravity>true</gravity>
      <velocity_decay />
      <visual />
    </link>
  </model>
</sdf>
"""

WIND_PATCH = """\
diff --git a/models/x500_base/model.sdf b/models/x500_base/model.sdf
--- a/models/x500_base/model.sdf
+++ b/models/x500_base/model.sdf
@@ -5,6 +5,7 @@
         <inertia>
         </inertia>
       </inertial>
       <gravity>true</gravity>
+      <enable_wind>true</enable_wind>
       <velocity_decay />
       <visual />
"""


def create_test_run(tmp_path: Path):
    return create_run_directory(
        tmp_path / "runs",
        run_id=RUN_ID,
        scenario_id="wind_tracking",
        started_at=STARTED_AT,
    )


def create_px4_model(tmp_path: Path) -> Path:
    repository = tmp_path / "PX4-Autopilot"
    model_directory = (
        repository
        / "Tools"
        / "simulation"
        / "gz"
        / "models"
        / "x500_base"
    )

    model_directory.mkdir(parents=True)

    (model_directory / "model.sdf").write_text(
        MODEL_SDF,
        encoding="utf-8",
    )
    (model_directory / "model.config").write_text(
        "<model />\n",
        encoding="utf-8",
    )

    mesh_directory = model_directory / "meshes"
    mesh_directory.mkdir()
    (mesh_directory / "frame.dae").write_bytes(
        b"test-mesh"
    )

    return repository


def write_snapshot_patch(
    run_directory,
) -> Path:
    patch_path = (
        run_directory.input_patches_dir
        / "x500_enable_wind.patch"
    )
    patch_path.write_text(
        WIND_PATCH,
        encoding="utf-8",
    )
    return patch_path


def test_prepares_patched_run_owned_model(
    tmp_path: Path,
) -> None:
    run_directory = create_test_run(tmp_path)
    repository = create_px4_model(tmp_path)
    patch_path = write_snapshot_patch(
        run_directory
    )

    source_sdf_path = (
        repository
        / "Tools"
        / "simulation"
        / "gz"
        / "models"
        / "x500_base"
        / "model.sdf"
    )
    source_before = source_sdf_path.read_bytes()

    prepared = prepare_wind_model_workspace(
        run_directory,
        px4_repository=repository,
        patch_path=patch_path,
    )

    assert prepared.models_root == (
        run_directory.workspace_dir / "models"
    )
    assert prepared.model_directory.is_dir()
    assert prepared.model_sdf_path.is_file()
    assert prepared.model_config_path.is_file()
    assert prepared.patch_path == (
        patch_path.resolve()
    )

    prepared_contents = (
        prepared.model_sdf_path.read_text(
            encoding="utf-8"
        )
    )
    assert (
        prepared_contents.count(
            "<enable_wind>true</enable_wind>"
        )
        == 1
    )

    assert (
        prepared.model_directory
        / "meshes"
        / "frame.dae"
    ).read_bytes() == b"test-mesh"

    assert source_sdf_path.read_bytes() == source_before
    assert (
        "<enable_wind>true</enable_wind>"
        not in source_sdf_path.read_text(
            encoding="utf-8"
        )
    )


def test_patch_must_be_snapshotted_input(
    tmp_path: Path,
) -> None:
    run_directory = create_test_run(tmp_path)
    repository = create_px4_model(tmp_path)

    outside_patch = tmp_path / "outside.patch"
    outside_patch.write_text(
        WIND_PATCH,
        encoding="utf-8",
    )

    with pytest.raises(
        WindWorkspaceError,
        match="snapshotted",
    ):
        prepare_wind_model_workspace(
            run_directory,
            px4_repository=repository,
            patch_path=outside_patch,
        )


def test_invalid_patch_leaves_no_model(
    tmp_path: Path,
) -> None:
    run_directory = create_test_run(tmp_path)
    repository = create_px4_model(tmp_path)

    patch_path = (
        run_directory.input_patches_dir
        / "x500_enable_wind.patch"
    )
    patch_path.write_text(
        "not a unified diff\n",
        encoding="utf-8",
    )

    with pytest.raises(
        WindWorkspaceError,
        match="check failed",
    ):
        prepare_wind_model_workspace(
            run_directory,
            px4_repository=repository,
            patch_path=patch_path,
        )

    assert not (
        run_directory.workspace_dir
        / "models"
        / "x500_base"
    ).exists()


def test_missing_model_config_is_rejected(
    tmp_path: Path,
) -> None:
    run_directory = create_test_run(tmp_path)
    repository = create_px4_model(tmp_path)
    patch_path = write_snapshot_patch(
        run_directory
    )

    model_config = (
        repository
        / "Tools"
        / "simulation"
        / "gz"
        / "models"
        / "x500_base"
        / "model.config"
    )
    model_config.unlink()

    with pytest.raises(
        WindWorkspaceError,
        match="model.config",
    ):
        prepare_wind_model_workspace(
            run_directory,
            px4_repository=repository,
            patch_path=patch_path,
        )


def test_existing_model_is_not_overwritten(
    tmp_path: Path,
) -> None:
    run_directory = create_test_run(tmp_path)
    repository = create_px4_model(tmp_path)
    patch_path = write_snapshot_patch(
        run_directory
    )

    first = prepare_wind_model_workspace(
        run_directory,
        px4_repository=repository,
        patch_path=patch_path,
    )

    original_contents = (
        first.model_sdf_path.read_bytes()
    )

    with pytest.raises(
        WindWorkspaceError,
        match="already exists",
    ):
        prepare_wind_model_workspace(
            run_directory,
            px4_repository=repository,
            patch_path=patch_path,
        )

    assert (
        first.model_sdf_path.read_bytes()
        == original_contents
    )