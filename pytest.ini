"""Небольшие интеграционные тесты основных направлений конвертации."""

from pathlib import Path

from nbtlib import File
from nbtlib.tag import ByteArray, Compound, Double, Int, IntArray, List, Short, String

from converter import (
    StructureData,
    build_3d_render_model,
    build_preview_map,
    load_schematic,
    load_structure_nbt,
    replace_blocks,
    rotate_structure,
    save_sponge_schematic,
    save_structure_nbt,
)
from utils import STANDARD_BLOCK_NAMES, autocomplete_block_names, make_block_state


def _save_classic(path: Path) -> None:
    root = Compound({
        "Materials": String("Alpha"),
        "Width": Short(2),
        "Height": Short(1),
        "Length": Short(2),
        "Blocks": ByteArray([1, 5, 35, 54]),
        "Data": ByteArray([0, 1, 14, 2]),
        "TileEntities": List[Compound]([
            Compound({"id": String("minecraft:chest"), "x": Int(1), "y": Int(0), "z": Int(1)})
        ]),
        "Entities": List[Compound]([
            Compound({
                "id": String("minecraft:armor_stand"),
                "Pos": List[Double]([Double(0.5), Double(1.0), Double(0.5)]),
            })
        ]),
    })
    File({"Schematic": root}, gzipped=True).save(str(path))


def test_classic_to_structure_roundtrip(tmp_path: Path) -> None:
    source = tmp_path / "house.schematic"
    output = tmp_path / "house.nbt"
    _save_classic(source)

    structure = load_schematic(source)
    assert (structure.width, structure.height, structure.length) == (2, 1, 2)
    assert structure.blocks[0].name == "minecraft:stone"
    assert structure.blocks[1].name == "minecraft:spruce_planks"
    assert structure.blocks[2].name == "minecraft:red_wool"
    assert len(structure.block_entities) == 1
    assert len(structure.entities) == 1

    structure, count = replace_blocks(structure, "minecraft:stone", "minecraft:deepslate")
    assert count == 1
    structure = rotate_structure(structure, 90)
    save_structure_nbt(structure, output)

    restored = load_structure_nbt(output)
    assert restored.blocks == structure.blocks
    assert restored.block_entities[0].pos == structure.block_entities[0].pos
    assert len(restored.entities) == 1


def test_structure_to_sponge_roundtrip(tmp_path: Path) -> None:
    classic = tmp_path / "source.schematic"
    nbt_path = tmp_path / "source.nbt"
    sponge_path = tmp_path / "source.schem"
    _save_classic(classic)
    original = load_schematic(classic)
    save_structure_nbt(original, nbt_path)

    structure = load_structure_nbt(nbt_path)
    save_sponge_schematic(structure, sponge_path)
    restored = load_schematic(sponge_path)

    assert restored.blocks == structure.blocks
    assert restored.palette == structure.palette
    assert len(restored.block_entities) == 1
    assert len(restored.entities) == 1


def test_sponge_v3_and_multibyte_varint(tmp_path: Path) -> None:
    source = tmp_path / "v3.schem"
    # ID 130 кодируется двумя байтами VarInt: 0x82, 0x01.
    palette = Compound({f"minecraft:test_{number}": Int(number) for number in range(131)})
    root = Compound({
        "Version": Int(3),
        "DataVersion": Int(3465),
        "Width": Short(1),
        "Height": Short(1),
        "Length": Short(1),
        "Blocks": Compound({
            "Palette": palette,
            "Data": ByteArray([-126, 1]),
            "BlockEntities": List[Compound]([]),
        }),
        "Entities": List[Compound]([]),
        "Offset": IntArray([0, 0, 0]),
    })
    File({"Schematic": root}, gzipped=True).save(str(source))

    structure = load_schematic(source)
    assert structure.source_format == "Sponge Schematic v3"
    assert structure.blocks[0].name == "minecraft:test_130"


def test_rotation_updates_coordinates_and_state(tmp_path: Path) -> None:
    source = tmp_path / "stairs.schem"
    root = Compound({
        "Version": Int(2),
        "Width": Short(2),
        "Height": Short(1),
        "Length": Short(3),
        "Palette": Compound({"minecraft:oak_stairs[facing=north,half=bottom]": Int(0)}),
        "BlockData": ByteArray([0, 0, 0, 0, 0, 0]),
        "BlockEntities": List[Compound]([]),
        "Entities": List[Compound]([]),
    })
    File({"Schematic": root}, gzipped=True).save(str(source))

    structure = rotate_structure(load_schematic(source), 90)
    assert (structure.width, structure.length) == (3, 2)
    assert all(block.props["facing"] == "east" for block in structure.blocks)


def test_preview_map_and_autocomplete(tmp_path: Path) -> None:
    source = tmp_path / "preview.schematic"
    _save_classic(source)
    structure = load_schematic(source)

    preview = build_preview_map(structure)
    assert preview.image.size == (2, 2)
    assert preview.block_at(0, 0)[0].name == "minecraft:stone"
    assert preview.block_at(0, 0)[1] == 0
    assert len(STANDARD_BLOCK_NAMES) > 900
    assert "minecraft:oak_stairs" in autocomplete_block_names("minecraft:oak_sta")


def test_large_3d_model_uses_simplified_limit() -> None:
    blocks = [make_block_state("minecraft:stone")] * 10001
    structure = StructureData(10001, 1, 1, blocks)

    model = build_3d_render_model(structure)
    assert model.simplified is True
    assert model.total_blocks == 10001
    assert len(model.blocks) == 5000
    # Равномерная выборка захватывает и начало, и конец длинной структуры.
    assert model.blocks[0].x == 0
    assert model.blocks[-1].x >= 9998
