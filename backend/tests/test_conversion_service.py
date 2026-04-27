from pathlib import Path
import json
import sys
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


from app.services.conversion_service import ConversionService


def test_sanitizes_bambu_project_settings(tmp_path: Path) -> None:
    source = tmp_path / "input.3mf"
    destination_dir = tmp_path / "out"
    destination_dir.mkdir()

    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "Metadata/project_settings.config",
            json.dumps(
                {
                    "raft_first_layer_expansion": "-1",
                    "solid_infill_filament": "0",
                    "sparse_infill_filament": "0",
                    "tree_support_wall_count": "-1",
                    "wall_filament": "0",
                    "use_relative_e_distances": "1",
                    "before_layer_change_gcode": "",
                    "machine_start_gcode": "Bambu specific",
                    "machine_end_gcode": "Bambu specific",
                    "change_filament_gcode": "M620",
                    "printer_model": "Bambu Lab P1S",
                    "printer_settings_id": "Bambu Lab P1S 0.4 nozzle",
                    "single_extruder_multi_material": "1",
                    "print_compatible_printers": ["Bambu Lab P1S 0.4 nozzle"],
                    "upward_compatible_machine": ["Bambu Lab P1S 0.4 nozzle"],
                    "filament_start_gcode": ["Bambu start"],
                    "filament_end_gcode": ["Bambu end"],
                    "timelapse_type": 0,
                    "enable_prime_tower": "1",
                    "wipe": ["1", "1"],
                    "wipe_distance": ["2", "2"],
                    "flush_into_support": "1",
                    "prime_tower_width": "35",
                    "wipe_tower_x": ["165"],
                    "wipe_tower_y": ["214.13"],
                }
            ),
        )
        archive.writestr("3D/3dmodel.model", "<model />")

    service = ConversionService()
    result = service.convert_to_snapmaker(source, destination_dir)

    with ZipFile(result["output_file"], "r") as archive:
        settings = json.loads(archive.read("Metadata/project_settings.config").decode("utf-8"))

    assert settings["raft_first_layer_expansion"] == "0"
    assert settings["tree_support_wall_count"] == "0"
    assert settings["solid_infill_filament"] == "1"
    assert settings["sparse_infill_filament"] == "1"
    assert settings["wall_filament"] == "1"
    assert settings["use_relative_e_distances"] == "0"
    assert settings["change_filament_gcode"] == ""
    assert settings["printer_model"] == "Snapmaker U1 0.4 nozzle"
    assert settings["printer_settings_id"] == "Snapmaker U1 0.4 nozzle"
    assert settings["single_extruder_multi_material"] == "0"
    assert settings["print_compatible_printers"] == ["Snapmaker U1 0.4 nozzle"]
    assert settings["upward_compatible_machine"] == ["Snapmaker U1 0.4 nozzle"]
    assert "M82" in settings["machine_start_gcode"]
    assert "M104 S0" in settings["machine_end_gcode"]
    assert settings["filament_start_gcode"] == ["; SnapMaker3d Studio sanitized filament start gcode\n"]
    assert settings["filament_end_gcode"] == ["; SnapMaker3d Studio sanitized filament end gcode\n"]
    assert "timelapse_type" not in settings
    assert settings["enable_prime_tower"] == "0"
    assert settings["wipe"] == ["0"]
    assert settings["wipe_distance"] == ["0"]
    assert settings["flush_into_support"] == "0"
    assert settings["prime_tower_width"] == "2"
    assert settings["wipe_tower_x"] == ["0"]
    assert settings["wipe_tower_y"] == ["0"]
    assert settings["before_layer_change_gcode"] == ""
    assert settings["layer_change_gcode"].strip() == "; layer {layer_num+1}"
    assert settings["printable_area"] == ["0x0", "270x0", "270x270", "0x270"]
    assert settings["plate_shape"] == ["0x0", "270x0", "270x270", "0x270"]
    assert settings["bed_exclude_area"] == []


def test_generates_incremental_export_names(tmp_path: Path) -> None:
    source = tmp_path / "input.3mf"
    destination_dir = tmp_path / "out"
    destination_dir.mkdir()

    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("Metadata/project_settings.config", json.dumps({}))
        archive.writestr("3D/3dmodel.model", "<model />")

    service = ConversionService()
    first = service.convert_to_snapmaker(source, destination_dir)
    second = service.convert_to_snapmaker(source, destination_dir)
    third = service.convert_to_snapmaker(source, destination_dir)

    assert Path(first["output_file"]).name == "input_snapmaker_compatible_final.3mf"
    assert Path(second["output_file"]).name == "input_snapmaker_compatible_01.3mf"
    assert Path(third["output_file"]).name == "input_snapmaker_compatible_02.3mf"


def test_stream_preserves_large_plate_based_archive_without_loading_all_entries(tmp_path: Path) -> None:
    source = tmp_path / "large_plate.3mf"
    destination_dir = tmp_path / "out"
    destination_dir.mkdir()

    model_settings = """<config><plate><model_instance id=\"1\"/></plate></config>"""
    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("Metadata/model_settings.config", model_settings)
        archive.writestr("Metadata/project_settings.config", json.dumps({"printer_model": "Bambu Lab P1S"}))
        archive.writestr("3D/3dmodel.model", "<model />")

    with ZipFile(source, "a", compression=ZIP_STORED) as archive:
        archive.writestr("3D/Objects/object_4.model", b"0" * (21 * 1024 * 1024))

    service = ConversionService()
    result = service.convert_to_snapmaker(source, destination_dir)

    assert Path(result["output_file"]).exists()
    assert any("streaming" in item.lower() or "plates" in item.lower() for item in result["adapted"])

    with ZipFile(result["output_file"], "r") as archive:
        assert "3D/Objects/object_4.model" in archive.namelist()
        settings = json.loads(archive.read("Metadata/project_settings.config").decode("utf-8"))
        assert settings["printer_model"] == "Snapmaker U1 0.4 nozzle"


def test_enables_supports_when_support_plan_requires_it(tmp_path: Path) -> None:
    source = tmp_path / "input.3mf"
    destination_dir = tmp_path / "out"
    destination_dir.mkdir()

    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("Metadata/project_settings.config", json.dumps({}))
        archive.writestr("3D/3dmodel.model", "<model />")

    service = ConversionService()
    result = service.convert_to_snapmaker(
        source,
        destination_dir,
        support_plan={
            "enabled": True,
            "type": "tree(auto)",
            "threshold_angle": 25,
            "build_plate_only": False,
            "reason": "critical_overhangs_detected",
        },
    )

    with ZipFile(result["output_file"], "r") as archive:
        settings = json.loads(archive.read("Metadata/project_settings.config").decode("utf-8"))

    assert settings["enable_support"] == "1"
    assert settings["support_type"] == "tree(auto)"
    assert settings["support_threshold_angle"] == "25"
    assert settings["support_remove_small_overhang"] == "0"


def test_applies_first_layer_adhesion_plan(tmp_path: Path) -> None:
    source = tmp_path / "input.3mf"
    destination_dir = tmp_path / "out"
    destination_dir.mkdir()

    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("Metadata/project_settings.config", json.dumps({}))
        archive.writestr("3D/3dmodel.model", "<model />")

    service = ConversionService()
    result = service.convert_to_snapmaker(
        source,
        destination_dir,
        adhesion_plan={
            "mode": "brim",
            "brim_width_mm": 8,
            "raft_layers": 0,
            "skirt_loops": 2,
            "initial_layer_speed_mm_s": 20,
            "initial_layer_infill_speed_mm_s": 20,
            "initial_layer_acceleration_mm_s2": 300,
            "initial_layer_flow_ratio": 1.04,
            "initial_layer_height_mm": 0.2,
            "reason": "reduced_contact_or_tall_geometry",
        },
    )

    with ZipFile(result["output_file"], "r") as archive:
        settings = json.loads(archive.read("Metadata/project_settings.config").decode("utf-8"))

    assert settings["brim_type"] == "auto_brim"
    assert settings["brim_width"] == "8"
    assert settings["skirt_loops"] == "2"
    assert settings["raft_layers"] == "0"
    assert settings["initial_layer_flow_ratio"] == "1.04"
    assert settings["initial_layer_print_height"] == "0.2"
    assert settings["initial_layer_speed"] == ["20"]
    assert settings["initial_layer_infill_speed"] == ["20"]
    assert settings["initial_layer_acceleration"] == ["300"]


def test_inlines_external_geometry_references_for_snapmaker_compatibility(tmp_path: Path) -> None:
    source = tmp_path / "input.3mf"
    destination_dir = tmp_path / "out"
    destination_dir.mkdir()

    root_model = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p">
  <resources>
    <object id="19" type="model">
      <components>
        <component p:path="/3D/Objects/object_1.model" objectid="1" transform="1 0 0 0 1 0 0 0 1 0 0 0" />
      </components>
    </object>
  </resources>
  <build>
    <item objectid="19" transform="1 0 0 0 1 0 0 0 1 10 20 30" printable="1" />
  </build>
</model>
"""
    external_model = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources>
    <object id="1" type="model">
      <mesh>
        <vertices>
          <vertex x="0" y="0" z="0" />
          <vertex x="10" y="0" z="0" />
          <vertex x="0" y="10" z="0" />
          <vertex x="0" y="0" z="10" />
        </vertices>
        <triangles>
          <triangle v1="0" v2="1" v3="2" />
          <triangle v1="0" v2="1" v3="3" />
          <triangle v1="0" v2="2" v3="3" />
          <triangle v1="1" v2="2" v3="3" />
        </triangles>
      </mesh>
    </object>
  </resources>
</model>
"""

    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("Metadata/project_settings.config", json.dumps({}))
        archive.writestr("3D/3dmodel.model", root_model)
        archive.writestr("3D/Objects/object_1.model", external_model)

    service = ConversionService()
    result = service.convert_to_snapmaker(source, destination_dir)

    with ZipFile(result["output_file"], "r") as archive:
        root = ET.fromstring(archive.read("3D/3dmodel.model"))

    ns = {
        "m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02",
        "p": "http://schemas.microsoft.com/3dmanufacturing/production/2015/06",
    }
    objects = root.findall("m:resources/m:object", ns)
    assert len(objects) == 1
    assert objects[0].find("m:mesh", ns) is not None
    assert root.findall(".//m:component", ns) == []


def test_removes_external_model_parts_when_root_is_self_contained(tmp_path: Path) -> None:
    source = tmp_path / "input.3mf"
    destination_dir = tmp_path / "out"
    destination_dir.mkdir()

    root_model = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p">
  <resources>
    <object id="19" type="model">
      <components>
        <component p:path="/3D/Objects/object_1.model" objectid="1" transform="1 0 0 0 1 0 0 0 1 0 0 0" />
      </components>
    </object>
  </resources>
  <build>
    <item objectid="19" transform="1 0 0 0 1 0 0 0 1 10 20 30" printable="1" />
  </build>
</model>
"""
    external_model = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources>
    <object id="1" type="model">
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
</model>
"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/Objects/object_1.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""

    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("Metadata/project_settings.config", json.dumps({}))
        archive.writestr("3D/3dmodel.model", root_model)
        archive.writestr("3D/Objects/object_1.model", external_model)
        archive.writestr("3D/_rels/3dmodel.model.rels", rels)

    service = ConversionService()
    result = service.convert_to_snapmaker(source, destination_dir)

    with ZipFile(result["output_file"], "r") as archive:
        names = archive.namelist()
        root = ET.fromstring(archive.read("3D/3dmodel.model"))

    assert "3D/_rels/3dmodel.model.rels" not in names
    assert not any(name.startswith("3D/Objects/") and name.endswith(".model") for name in names)
    assert "requiredextensions" not in root.attrib


def test_flattens_composite_build_items_into_direct_mesh_items(tmp_path: Path) -> None:
    source = tmp_path / "input.3mf"
    destination_dir = tmp_path / "out"
    destination_dir.mkdir()

    root_model = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources>
    <object id="10" type="model">
      <components>
        <component objectid="20" transform="1 0 0 0 1 0 0 0 1 1 2 3" />
        <component objectid="21" transform="1 0 0 0 1 0 0 0 1 4 5 6" />
      </components>
    </object>
    <object id="20" type="model">
      <mesh>
        <vertices>
          <vertex x="0" y="0" z="0" />
          <vertex x="10" y="0" z="0" />
          <vertex x="0" y="10" z="0" />
          <vertex x="0" y="0" z="10" />
        </vertices>
        <triangles>
          <triangle v1="0" v2="1" v3="2" />
          <triangle v1="0" v2="1" v3="3" />
          <triangle v1="0" v2="2" v3="3" />
          <triangle v1="1" v2="2" v3="3" />
        </triangles>
      </mesh>
    </object>
    <object id="21" type="model">
      <mesh>
        <vertices>
          <vertex x="0" y="0" z="0" />
          <vertex x="5" y="0" z="0" />
          <vertex x="0" y="5" z="0" />
          <vertex x="0" y="0" z="5" />
        </vertices>
        <triangles>
          <triangle v1="0" v2="1" v3="2" />
          <triangle v1="0" v2="1" v3="3" />
          <triangle v1="0" v2="2" v3="3" />
          <triangle v1="1" v2="2" v3="3" />
        </triangles>
      </mesh>
    </object>
  </resources>
  <build>
    <item objectid="10" transform="1 0 0 0 1 0 0 0 1 7 8 9" printable="1" />
  </build>
</model>
"""

    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("Metadata/project_settings.config", json.dumps({}))
        archive.writestr("3D/3dmodel.model", root_model)

    service = ConversionService()
    result = service.convert_to_snapmaker(source, destination_dir)

    with ZipFile(result["output_file"], "r") as archive:
        root = ET.fromstring(archive.read("3D/3dmodel.model"))

    ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    items = root.findall("m:build/m:item", ns)
    assert len(items) == 2
    assert {item.attrib["objectid"] for item in items} == {"1", "2"}
    assert all("transform" not in item.attrib for item in items)
    for item in items:
        baked_object = root.find(f"m:resources/m:object[@id='{item.attrib['objectid']}']", ns)
        assert baked_object is not None
        triangles = baked_object.findall("m:mesh/m:triangles/m:triangle", ns)
        vertices = baked_object.findall("m:mesh/m:vertices/m:vertex", ns)
        assert len(vertices) == 4
        assert len(triangles) == 4


def test_splits_overflowed_plate_and_grounds_items(tmp_path: Path) -> None:
    source = tmp_path / "input.3mf"
    destination_dir = tmp_path / "out"
    destination_dir.mkdir()

    root_model = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p">
  <resources>
    <object id="2" type="model">
      <components>
        <component p:path="/3D/Objects/object_1.model" objectid="1" transform="1 0 0 0 1 0 0 0 1 0 0 0" />
      </components>
    </object>
    <object id="4" type="model">
      <components>
        <component p:path="/3D/Objects/object_2.model" objectid="3" transform="1 0 0 0 1 0 0 0 1 0 0 0" />
      </components>
    </object>
  </resources>
  <build>
    <item objectid="2" transform="1 0 0 0 1 0 0 0 1 0 0 10" printable="1" />
    <item objectid="4" transform="1 0 0 0 1 0 0 0 1 400 0 20" printable="1" />
  </build>
</model>
"""
    object_model_template = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources>
    <object id="{object_id}" type="model">
      <mesh>
        <vertices>
          <vertex x="0" y="0" z="0" />
          <vertex x="10" y="0" z="0" />
          <vertex x="0" y="10" z="0" />
          <vertex x="0" y="0" z="10" />
        </vertices>
        <triangles>
          <triangle v1="0" v2="1" v3="2" />
          <triangle v1="0" v2="1" v3="3" />
          <triangle v1="0" v2="2" v3="3" />
          <triangle v1="1" v2="2" v3="3" />
        </triangles>
      </mesh>
    </object>
  </resources>
</model>
"""

    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("Metadata/project_settings.config", json.dumps({}))
        archive.writestr("3D/3dmodel.model", root_model)
        archive.writestr("3D/Objects/object_1.model", object_model_template.format(object_id="1"))
        archive.writestr("3D/Objects/object_2.model", object_model_template.format(object_id="3"))

    service = ConversionService()
    result = service.convert_to_snapmaker(source, destination_dir)

    assert result["extra_output_files"] == []

    with ZipFile(result["output_file"], "r") as archive:
        names = archive.namelist()
        settings = json.loads(archive.read("Metadata/project_settings.config").decode("utf-8"))
        root = ET.fromstring(archive.read("3D/3dmodel.model"))
        rels_xml = archive.read("_rels/.rels").decode("utf-8")
        content_types_xml = archive.read("[Content_Types].xml").decode("utf-8")
    ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    items = root.findall("m:build/m:item", ns)
    assert len(items) == 2
    assert all("transform" not in item.attrib for item in items)
    assert "Metadata/model_settings.config" not in names
    assert "3D/_rels/3dmodel.model.rels" not in names
    assert settings["prime_tower_width"] == "2"
    assert settings["raft_first_layer_expansion"] == "0"

    vertices = root.findall("m:resources/m:object/m:mesh/m:vertices/m:vertex", ns)
    xs = [float(vertex.attrib["x"]) for vertex in vertices]
    ys = [float(vertex.attrib["y"]) for vertex in vertices]
    assert min(xs) >= 0.0
    assert min(ys) >= 0.0
    assert max(xs) <= 270.0
    assert max(ys) <= 270.0
    assert "ns0:" not in rels_xml
    assert "ns0:" not in content_types_xml
    assert 'Target="3D/3dmodel.model"' in rels_xml


def test_preserves_bambu_plate_structure_when_model_settings_define_multiple_plates(tmp_path: Path) -> None:
    source = tmp_path / "input.3mf"
    destination_dir = tmp_path / "out"
    destination_dir.mkdir()

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
    <object id="4" type="model">
      <mesh>
        <vertices>
          <vertex x="0" y="0" z="0" />
          <vertex x="8" y="0" z="0" />
          <vertex x="0" y="8" z="0" />
        </vertices>
        <triangles>
          <triangle v1="0" v2="1" v3="2" />
        </triangles>
      </mesh>
    </object>
  </resources>
  <build>
    <item objectid="2" transform="1 0 0 0 1 0 0 0 1 20 30 0" printable="1" />
    <item objectid="4" transform="1 0 0 0 1 0 0 0 1 220 140 0" printable="1" />
  </build>
</model>
"""
    model_settings = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="2"><metadata key="name" value="A"/></object>
  <object id="4"><metadata key="name" value="B"/></object>
  <plate>
    <metadata key="plater_id" value="1"/>
    <metadata key="thumbnail_file" value="Metadata/plate_1.png"/>
    <model_instance>
      <metadata key="object_id" value="2"/>
      <metadata key="instance_id" value="0"/>
      <metadata key="identify_id" value="1001"/>
    </model_instance>
  </plate>
  <plate>
    <metadata key="plater_id" value="2"/>
    <metadata key="thumbnail_file" value="Metadata/plate_2.png"/>
    <model_instance>
      <metadata key="object_id" value="4"/>
      <metadata key="instance_id" value="0"/>
      <metadata key="identify_id" value="1002"/>
    </model_instance>
  </plate>
</config>
"""

    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("3D/3dmodel.model", root_model)
        archive.writestr("Metadata/project_settings.config", json.dumps({}))
        archive.writestr("Metadata/model_settings.config", model_settings)
        archive.writestr("Metadata/filament_sequence.json", '{"plate_1":{"sequence":[]},"plate_2":{"sequence":[]}}')
        archive.writestr("Metadata/plate_1.png", b"fakepng1")
        archive.writestr("Metadata/plate_2.png", b"fakepng2")

    service = ConversionService()
    result = service.convert_to_snapmaker(source, destination_dir)

    with ZipFile(result["output_file"], "r") as archive:
        names = set(archive.namelist())
        root = ET.fromstring(archive.read("3D/3dmodel.model"))
        preserved_model_settings = ET.fromstring(archive.read("Metadata/model_settings.config"))

    assert "Metadata/model_settings.config" in names
    assert "Metadata/filament_sequence.json" in names
    assert "Metadata/plate_1.png" in names
    assert "Metadata/plate_2.png" in names

    ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    items = root.findall("m:build/m:item", ns)
    assert len(items) == 2
    assert [item.attrib["objectid"] for item in items] == ["2", "4"]
    assert items[0].attrib["transform"] == "1 0 0 0 1 0 0 0 1 20 30 0"
    assert items[1].attrib["transform"] == "1 0 0 0 1 0 0 0 1 220 140 0"

    plates = preserved_model_settings.findall("plate")
    assert len(plates) == 2
    first_plate_instances = plates[0].findall("model_instance")
    second_plate_instances = plates[1].findall("model_instance")
    assert first_plate_instances[0].find("metadata[@key='object_id']").attrib["value"] == "2"
    assert second_plate_instances[0].find("metadata[@key='object_id']").attrib["value"] == "4"
