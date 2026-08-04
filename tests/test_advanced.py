"""Integration tests for Litematic, editing, plugins and mesh export."""

from pathlib import Path

from nbtlib import File
from nbtlib.tag import Compound, Int, List, LongArray, String

from advanced import EditSession, PluginManager, block_layer, block_statistics
from converter import (
    StructureData,
    convert_file,
    extract_region,
    load_litematic,
    load_schematic,
    save_litematic,
    _pack_litematic_indices,
)
from mesh_export import export_obj, export_stl
from utils import make_block_state


def _palette_structure() -> StructureData:
    palette = [make_block_state("air")] + [make_block_state(f"test:block_{index}") for index in range(20)]
    blocks = [palette[(index * 11) % len(palette)] for index in range(7 * 5 * 9)]
    return StructureData(7, 5, 9, blocks)


def test_litematic_cross_long_roundtrip_and_dispatch(tmp_path: Path) -> None:
    original = _palette_structure()
    litematic = save_litematic(original, tmp_path / "source.litematic")
    restored = load_litematic(litematic)

    assert (restored.width, restored.height, restored.length) == (7, 5, 9)
    assert restored.blocks == original.blocks

    nbt_path = tmp_path / "converted.nbt"
    result, converted, replacements = convert_file(litematic, nbt_path)
    assert result == nbt_path
    assert converted.blocks == original.blocks
    assert replacements == 0

    schematic_path = tmp_path / "cropped.schematic"
    convert_file(litematic, schematic_path, region=((1, 1, 1), (3, 3, 4)))
    schematic = load_schematic(schematic_path)
    assert (schematic.width, schematic.height, schematic.length) == (3, 3, 4)


def test_negative_litematic_region_keeps_block_orientation(tmp_path: Path) -> None:
    path = tmp_path / "negative.litematic"
    palette = List[Compound]([
        Compound({"Name": String("minecraft:air")}),
        Compound({"Name": String("minecraft:stone")}),
        Compound({"Name": String("minecraft:gold_block")}),
    ])
    # For Size.x=-3, storage x=0 maps to schematic x=-2 and storage x=2 to x=0.
    region = Compound({
        "Position": Compound({"x": Int(10), "y": Int(0), "z": Int(0)}),
        "Size": Compound({"x": Int(-3), "y": Int(1), "z": Int(1)}),
        "BlockStatePalette": palette,
        "BlockStates": LongArray(_pack_litematic_indices([1, 0, 2], 2)),
        "Entities": List[Compound]([]),
        "TileEntities": List[Compound]([]),
    })
    root = Compound({
        "Version": Int(6), "SubVersion": Int(1), "MinecraftDataVersion": Int(3465),
        "Regions": Compound({"negative": region}),
    })
    File({"": root}, gzipped=True).save(str(path))

    restored = load_litematic(path)
    assert [block.name for block in restored.blocks] == [
        "minecraft:stone", "minecraft:air", "minecraft:gold_block",
    ]


def test_region_extract_and_edit_history() -> None:
    air = make_block_state("air")
    structure = StructureData(5, 4, 5, [air] * 100)
    editor = EditSession(structure)

    assert editor.brush((2, 2, 2), "minecraft:stone", radius=1) == 7
    editor.set_selection((1, 1, 1), (3, 3, 3))
    copied = editor.copy_selection()
    assert copied.volume == 27
    cut_count = editor.cut_selection()
    assert cut_count == 7
    assert editor.undo() == "Fill selection"
    assert editor.redo() == "Fill selection"
    assert editor.paste((0, 0, 0)) == 7

    region = extract_region(editor.structure, (0, 0, 0), (2, 2, 2))
    assert (region.width, region.height, region.length) == (3, 3, 3)
    assert block_statistics(region, "stone")[0][1] == 7
    assert block_layer("minecraft:dirt") == "terrain"
    assert block_layer("minecraft:redstone_wire") == "redstone"


def test_stl_and_textured_obj_export(tmp_path: Path) -> None:
    stone = make_block_state("stone")
    structure = StructureData(2, 1, 1, [stone, stone])
    stl = export_stl(structure, tmp_path / "model.stl")
    obj = export_obj(structure, tmp_path / "model.obj")

    # Two adjacent cubes expose ten quads, or twenty STL triangles.
    assert stl.stat().st_size == 84 + 20 * 50
    obj_text = obj.read_text(encoding="utf-8")
    assert "mtllib model.mtl" in obj_text
    assert "usemtl blocks" in obj_text
    assert (tmp_path / "model.mtl").is_file()
    assert (tmp_path / "model_textures" / "atlas.png").is_file()


def test_plugin_discovery_and_execution(tmp_path: Path) -> None:
    plugin_folder = tmp_path / "plugins"
    plugin_folder.mkdir()
    (plugin_folder / "replace.py").write_text(
        "PLUGIN_NAME = 'Stone to gold'\n"
        "PLUGIN_DESCRIPTION = 'Test transform'\n"
        "def process(structure, api):\n"
        "    stone = api['make_block_state']('stone')\n"
        "    gold = api['make_block_state']('gold_block')\n"
        "    structure.blocks = [gold if block == stone else block for block in structure.blocks]\n"
        "    return structure\n",
        encoding="utf-8",
    )
    manager = PluginManager(plugin_folder)
    assert "Stone to gold" in manager.discover()
    source = StructureData(1, 1, 1, [make_block_state("stone")])
    result = manager.run("Stone to gold", source)
    assert result.blocks[0].name == "minecraft:gold_block"
    assert source.blocks[0].name == "minecraft:stone"
