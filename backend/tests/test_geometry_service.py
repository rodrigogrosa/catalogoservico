from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile


from app.services.mesh_analysis_service import MeshAnalysisService


def test_3mf_analysis_uses_lightweight_archive_path(tmp_path: Path) -> None:
    source = tmp_path / "input.3mf"
    root_model = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources>
    <object id="2" type="model">
      <mesh>
        <vertices>
          <vertex x="0" y="0" z="0" />
          <vertex x="10" y="0" z="0" />
          <vertex x="0" y="10" z="0" />
        </vertices>
        <triangles>
          <triangle v1="0" v2="1" v3="2" />
        </triangles>
      </mesh>
    </object>
  </resources>
  <build>
    <item objectid="2" printable="1" />
  </build>
</model>
"""
    model_settings = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <plate>
    <metadata key="plater_id" value="1"/>
    <model_instance>
      <metadata key="object_id" value="2"/>
      <metadata key="instance_id" value="0"/>
    </model_instance>
  </plate>
</config>
"""

    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("3D/3dmodel.model", root_model)
        archive.writestr("Metadata/model_settings.config", model_settings)
        archive.writestr("Metadata/project_settings.config", "{}")

    result = MeshAnalysisService().analyze(source)

    assert result["status"] == "ok"
    assert result["can_repair"] is False
    assert result["metrics"]["build_item_count"] == 1
    assert result["metrics"]["plate_count"] == 1
    assert any("modo leve" in risk.lower() for risk in result["risks"])
