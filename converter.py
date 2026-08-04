"""Чтение схем Minecraft и преобразование в формат структурных блоков.

Поддерживаются:
* классические MCEdit/WorldEdit ``.schematic`` (Blocks/Data/AddBlocks);
* Sponge Schematic v1/v2 (Palette + BlockData);
* Sponge Schematic v3 (Blocks/Palette/Data);
* ванильные Java Structure ``.nbt`` для обратной конвертации в Sponge v2.
"""

from __future__ import annotations

import copy
import math
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List as PyList, Optional, Sequence, Tuple, Union

import nbtlib
from nbtlib import File
from nbtlib.tag import ByteArray, Compound, Double, Int, IntArray, List, Long, LongArray, Short, String

from utils import (
    BlockState,
    LEGACY_NAMES,
    block_color,
    legacy_block_state,
    make_block_state,
    parse_block_state,
    rotate_block_state,
    state_matches,
    unique_states,
)


DEFAULT_DATA_VERSION = 3465  # Minecraft Java 1.20.1; новые версии применят DataFixer.
ProgressCallback = Optional[Callable[[int, str], None]]


class ConversionError(Exception):
    """Понятная пользователю ошибка чтения или преобразования."""


@dataclass
class BlockEntityData:
    pos: Tuple[int, int, int]
    nbt: Compound


@dataclass
class EntityData:
    pos: Tuple[float, float, float]
    block_pos: Tuple[int, int, int]
    nbt: Compound


@dataclass
class StructureData:
    width: int
    height: int
    length: int
    blocks: PyList[BlockState]
    block_entities: PyList[BlockEntityData] = field(default_factory=list)
    entities: PyList[EntityData] = field(default_factory=list)
    data_version: int = DEFAULT_DATA_VERSION
    source_format: str = "Неизвестный"
    warnings: PyList[str] = field(default_factory=list)

    @property
    def volume(self) -> int:
        return self.width * self.height * self.length

    @property
    def palette(self) -> Tuple[BlockState, ...]:
        return unique_states(self.blocks)

    def index(self, x: int, y: int, z: int) -> int:
        return (y * self.length + z) * self.width + x

    def validate(self) -> None:
        if min(self.width, self.height, self.length) <= 0:
            raise ConversionError("Размеры постройки должны быть больше нуля.")
        if len(self.blocks) != self.volume:
            raise ConversionError(
                f"Ожидалось {self.volume} блоков, но найдено {len(self.blocks)}. "
                "Возможно, файл повреждён или использует неподдерживаемую версию формата."
            )


@dataclass
class PreviewMap:
    """Данные интерактивного вида сверху для GUI."""

    image: Any
    width: int
    length: int
    top_blocks: Tuple[Optional[BlockState], ...]
    heights: Tuple[int, ...]

    def block_at(self, x: int, z: int) -> Tuple[Optional[BlockState], int]:
        if not (0 <= x < self.width and 0 <= z < self.length):
            return None, -1
        index = z * self.width + x
        return self.top_blocks[index], self.heights[index]


@dataclass(frozen=True)
class RenderBlock3D:
    """Один цветной куб для оптимизированного 3D-предпросмотра."""

    x: int
    y: int
    z: int
    color: Tuple[float, float, float]


@dataclass(frozen=True)
class RenderModel3D:
    """Подготовленная модель и сведения об упрощённом режиме."""

    blocks: Tuple[RenderBlock3D, ...]
    total_blocks: int
    simplified: bool
    width: int
    height: int
    length: int


def _progress(callback: ProgressCallback, value: int, message: str) -> None:
    if callback:
        callback(max(0, min(100, value)), message)


def _deep_compound(tag: object) -> Compound:
    if not isinstance(tag, Compound):
        return Compound()
    return copy.deepcopy(tag)


def _load_root(path: Path) -> Compound:
    try:
        nbt_file = nbtlib.load(str(path))
    except (OSError, ValueError, TypeError, EOFError) as exc:
        raise ConversionError(f"Не удалось прочитать NBT-файл: {exc}") from exc

    # nbtlib 1.x хранит корневой TAG_Compound в свойстве root.
    root = getattr(nbt_file, "root", nbt_file)
    if not isinstance(root, Compound):
        raise ConversionError("Корневой тег NBT должен быть TAG_Compound.")

    # Некоторые инструменты создают безымянный корень, внутри которого лежит Schematic.
    nested = root.get("Schematic")
    if isinstance(nested, Compound) and ("Width" in nested or "Blocks" in nested):
        return nested
    return root


def _dimensions(root: Compound) -> Tuple[int, int, int]:
    try:
        width = int(root["Width"])
        height = int(root["Height"])
        length = int(root["Length"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ConversionError("В схеме отсутствуют корректные Width, Height и Length.") from exc
    if min(width, height, length) <= 0:
        raise ConversionError(f"Некорректный размер схемы: {width} × {height} × {length}.")
    return width, height, length


def _decode_varints(values: Iterable[int], expected: int) -> PyList[int]:
    """Декодирует беззнаковые VarInt из Sponge BlockData."""

    result: PyList[int] = []
    value = 0
    shift = 0
    for raw in values:
        byte = int(raw) & 0xFF
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
            if shift >= 35:
                raise ConversionError("В BlockData обнаружен слишком длинный VarInt.")
        else:
            result.append(value)
            value = 0
            shift = 0
    if shift:
        raise ConversionError("BlockData заканчивается незавершённым VarInt.")
    if len(result) != expected:
        raise ConversionError(f"BlockData содержит {len(result)} индексов вместо ожидаемых {expected}.")
    return result


def _encode_varints(values: Iterable[int]) -> PyList[int]:
    result: PyList[int] = []
    for number in values:
        value = int(number)
        if value < 0:
            raise ConversionError("Индекс палитры не может быть отрицательным.")
        while True:
            byte = value & 0x7F
            value >>= 7
            if value:
                byte |= 0x80
            result.append(byte if byte < 128 else byte - 256)
            if not value:
                break
    return result


def _read_block_entities(tags: object) -> PyList[BlockEntityData]:
    result: PyList[BlockEntityData] = []
    if not isinstance(tags, (list, List)):
        return result
    for item in tags:
        if not isinstance(item, Compound):
            continue
        raw_pos = item.get("Pos")
        if raw_pos is None:
            raw_pos = item.get("pos")
        if isinstance(raw_pos, (list, List, IntArray)) and len(raw_pos) >= 3:
            pos = tuple(int(raw_pos[i]) for i in range(3))
        elif all(axis in item for axis in ("x", "y", "z")):
            pos = (int(item["x"]), int(item["y"]), int(item["z"]))
        else:
            continue
        data = _deep_compound(item.get("nbt", item))
        for key in ("Pos", "pos", "x", "y", "z"):
            data.pop(key, None)
        if "Id" in data and "id" not in data:
            data["id"] = String(str(data.pop("Id")))
        result.append(BlockEntityData(pos, data))
    return result


def _read_entities(tags: object) -> PyList[EntityData]:
    result: PyList[EntityData] = []
    if not isinstance(tags, (list, List)):
        return result
    for item in tags:
        if not isinstance(item, Compound):
            continue
        wrapped = isinstance(item.get("nbt"), Compound)
        data = _deep_compound(item.get("nbt", item))
        raw_pos = item.get("pos") if wrapped else item.get("Pos", item.get("pos"))
        if not isinstance(raw_pos, (list, List, IntArray)) or len(raw_pos) < 3:
            raw_pos = data.get("Pos")
        if not isinstance(raw_pos, (list, List, IntArray)) or len(raw_pos) < 3:
            continue
        pos = tuple(float(raw_pos[i]) for i in range(3))
        raw_block_pos = item.get("blockPos") if wrapped else None
        if isinstance(raw_block_pos, (list, List, IntArray)) and len(raw_block_pos) >= 3:
            block_pos = tuple(int(raw_block_pos[i]) for i in range(3))
        else:
            block_pos = tuple(math.floor(value) for value in pos)
        data.pop("Pos", None)
        data.pop("pos", None)
        result.append(EntityData(pos, block_pos, data))
    return result


def _read_classic(root: Compound, progress: ProgressCallback) -> StructureData:
    width, height, length = _dimensions(root)
    volume = width * height * length
    raw_blocks = root.get("Blocks")
    if not isinstance(raw_blocks, ByteArray):
        raise ConversionError("Классическая схема не содержит массив Blocks.")
    if len(raw_blocks) != volume:
        raise ConversionError(f"Массив Blocks содержит {len(raw_blocks)} значений вместо {volume}.")

    raw_data = root.get("Data")
    metadata = [int(value) & 0xFF for value in raw_data] if isinstance(raw_data, ByteArray) else [0] * volume
    if len(metadata) != volume:
        raise ConversionError(f"Массив Data содержит {len(metadata)} значений вместо {volume}.")
    add_blocks = root.get("AddBlocks")
    unknown_ids = set()
    blocks: PyList[BlockState] = []
    for index, raw_id in enumerate(raw_blocks):
        block_id = int(raw_id) & 0xFF
        if isinstance(add_blocks, ByteArray) and index // 2 < len(add_blocks):
            packed = int(add_blocks[index // 2]) & 0xFF
            block_id |= ((packed & 0x0F) if index % 2 == 0 else (packed >> 4)) << 8
        if block_id not in LEGACY_NAMES:
            unknown_ids.add(block_id)
        blocks.append(legacy_block_state(block_id, metadata[index]))
        if index and index % max(1, volume // 20) == 0:
            _progress(progress, 10 + int(index / volume * 45), "Преобразование числовых ID…")

    warnings: PyList[str] = []
    if unknown_ids:
        warnings.append("Неизвестные legacy ID заменены на barrier: " + ", ".join(map(str, sorted(unknown_ids))))
    structure = StructureData(
        width, height, length, blocks,
        _read_block_entities(root.get("TileEntities", root.get("BlockEntities"))),
        _read_entities(root.get("Entities")),
        int(root.get("DataVersion", DEFAULT_DATA_VERSION)),
        "MCEdit / WorldEdit (классический)", warnings,
    )
    structure.validate()
    return structure


def _read_sponge(root: Compound, progress: ProgressCallback) -> StructureData:
    width, height, length = _dimensions(root)
    volume = width * height * length
    block_section = root.get("Blocks") if isinstance(root.get("Blocks"), Compound) else root
    assert isinstance(block_section, Compound)
    palette_tag = block_section.get("Palette", root.get("Palette"))
    if not isinstance(palette_tag, Compound):
        raise ConversionError("Sponge-схема не содержит Compound-палитру Palette.")

    palette_by_id: Dict[int, BlockState] = {}
    try:
        for state_text, palette_id in palette_tag.items():
            palette_by_id[int(palette_id)] = parse_block_state(str(state_text))
    except (TypeError, ValueError) as exc:
        raise ConversionError(f"Некорректная палитра Sponge: {exc}") from exc
    if not palette_by_id:
        raise ConversionError("Палитра Sponge пуста.")

    data_tag = block_section.get("Data", root.get("BlockData"))
    direct_ids = root.get("BlockIDs")
    if isinstance(data_tag, ByteArray):
        indices = _decode_varints(data_tag, volume)
    elif isinstance(direct_ids, (ByteArray, IntArray, list, List)):
        indices = [int(value) & 0xFF if isinstance(direct_ids, ByteArray) else int(value) for value in direct_ids]
        if len(indices) != volume:
            raise ConversionError(f"BlockIDs содержит {len(indices)} индексов вместо {volume}.")
    elif isinstance(data_tag, (IntArray, list, List)):
        indices = [int(value) for value in data_tag]
        if len(indices) != volume:
            raise ConversionError(f"Data содержит {len(indices)} индексов вместо {volume}.")
    else:
        raise ConversionError("Sponge-схема не содержит BlockData/Blocks.Data.")

    blocks: PyList[BlockState] = []
    for index, palette_id in enumerate(indices):
        try:
            blocks.append(palette_by_id[palette_id])
        except KeyError as exc:
            raise ConversionError(f"Индекс {palette_id} из BlockData отсутствует в Palette.") from exc
        if index and index % max(1, volume // 20) == 0:
            _progress(progress, 15 + int(index / volume * 40), "Чтение палитры Sponge…")

    version = int(root.get("Version", 2))
    block_entities = block_section.get("BlockEntities", root.get("BlockEntities", root.get("TileEntities")))
    structure = StructureData(
        width, height, length, blocks,
        _read_block_entities(block_entities),
        _read_entities(root.get("Entities")),
        int(root.get("DataVersion", DEFAULT_DATA_VERSION)),
        f"Sponge Schematic v{version}",
    )
    structure.validate()
    return structure


def load_schematic(path: Union[str, Path], progress: ProgressCallback = None) -> StructureData:
    """Загружает classic/Sponge schematic и возвращает единое представление."""

    source = Path(path)
    if not source.is_file():
        raise ConversionError(f"Файл не найден: {source}")
    if source.suffix.lower() not in (".schematic", ".schem"):
        raise ConversionError("Ожидается файл с расширением .schematic или .schem.")
    _progress(progress, 3, "Открытие NBT…")
    root = _load_root(source)
    if isinstance(root.get("Blocks"), ByteArray) and not isinstance(root.get("Palette"), Compound):
        structure = _read_classic(root, progress)
    elif isinstance(root.get("Palette"), Compound) or isinstance(root.get("Blocks"), Compound):
        structure = _read_sponge(root, progress)
    else:
        raise ConversionError("Формат схемы не распознан: нет classic Blocks или Sponge Palette.")
    _progress(progress, 60, "Схема загружена")
    return structure


def load_structure_nbt(path: Union[str, Path], progress: ProgressCallback = None) -> StructureData:
    """Читает ванильную Java Structure NBT для обратной конвертации."""

    source = Path(path)
    if not source.is_file():
        raise ConversionError(f"Файл не найден: {source}")
    if source.suffix.lower() != ".nbt":
        raise ConversionError("Ожидается файл с расширением .nbt.")
    _progress(progress, 4, "Открытие Structure NBT…")
    root = _load_root(source)
    try:
        size = root["size"]
        width, height, length = (int(size[0]), int(size[1]), int(size[2]))
    except (KeyError, TypeError, IndexError, ValueError) as exc:
        raise ConversionError("Structure NBT не содержит корректный список size.") from exc
    volume = width * height * length
    palette_tag = root.get("palette")
    if not isinstance(palette_tag, (list, List)):
        raise ConversionError("Structure NBT не содержит список palette.")
    palette: PyList[BlockState] = []
    for entry in palette_tag:
        if not isinstance(entry, Compound) or "Name" not in entry:
            raise ConversionError("Некорректная запись в palette.")
        properties_tag = entry.get("Properties")
        properties = {str(key): str(value) for key, value in properties_tag.items()} if isinstance(properties_tag, Compound) else {}
        palette.append(make_block_state(str(entry["Name"]), properties))

    air = make_block_state("minecraft:air")
    blocks = [air] * volume
    block_entities: PyList[BlockEntityData] = []
    block_tags = root.get("blocks")
    if not isinstance(block_tags, (list, List)):
        raise ConversionError("Structure NBT не содержит список blocks.")
    for number, entry in enumerate(block_tags):
        if not isinstance(entry, Compound):
            continue
        try:
            x, y, z = (int(entry["pos"][0]), int(entry["pos"][1]), int(entry["pos"][2]))
            state = int(entry["state"])
            if not (0 <= x < width and 0 <= y < height and 0 <= z < length):
                continue
            blocks[(y * length + z) * width + x] = palette[state]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ConversionError(f"Некорректная запись blocks #{number}.") from exc
        if isinstance(entry.get("nbt"), Compound):
            block_entities.append(BlockEntityData((x, y, z), _deep_compound(entry["nbt"])))

    structure = StructureData(
        width, height, length, blocks, block_entities, _read_entities(root.get("entities")),
        int(root.get("DataVersion", DEFAULT_DATA_VERSION)), "Minecraft Java Structure NBT",
    )
    structure.validate()
    _progress(progress, 60, "Structure NBT загружена")
    return structure


def _xyz_compound(tag: object, label: str) -> Tuple[int, int, int]:
    """Read an x/y/z compound used by the Litematica format."""

    if isinstance(tag, Compound) and all(axis in tag for axis in ("x", "y", "z")):
        return int(tag["x"]), int(tag["y"]), int(tag["z"])
    if isinstance(tag, (list, List, IntArray)) and len(tag) >= 3:
        return int(tag[0]), int(tag[1]), int(tag[2])
    raise ConversionError(f"Litematic contains an invalid {label} tag.")


def _unpack_litematic_indices(values: Iterable[int], volume: int, bits: int) -> PyList[int]:
    """Decode palette indices packed continuously into signed Java long values."""

    if bits <= 0 or bits > 32:
        raise ConversionError(f"Unsupported Litematic palette width: {bits} bits.")
    words = [int(value) & 0xFFFFFFFFFFFFFFFF for value in values]
    expected_words = (volume * bits + 63) // 64
    if len(words) < expected_words:
        raise ConversionError(
            f"Litematic BlockStates contains {len(words)} long values instead of at least {expected_words}."
        )
    mask = (1 << bits) - 1
    result: PyList[int] = []
    for index in range(volume):
        bit_index = index * bits
        word_index, offset = divmod(bit_index, 64)
        value = words[word_index] >> offset
        spill = offset + bits - 64
        if spill > 0:
            value |= words[word_index + 1] << (bits - spill)
        result.append(value & mask)
    return result


def _pack_litematic_indices(values: Sequence[int], bits: int) -> PyList[int]:
    """Pack palette indices into signed Java long values without per-long padding."""

    if bits <= 0 or bits > 32:
        raise ConversionError(f"Unsupported Litematic palette width: {bits} bits.")
    mask = (1 << bits) - 1
    words = [0] * ((len(values) * bits + 63) // 64)
    for index, raw_value in enumerate(values):
        value = int(raw_value)
        if value < 0 or value > mask:
            raise ConversionError(f"Palette index {value} cannot be stored in {bits} bits.")
        bit_index = index * bits
        word_index, offset = divmod(bit_index, 64)
        words[word_index] |= (value << offset) & 0xFFFFFFFFFFFFFFFF
        if offset + bits > 64:
            words[word_index + 1] |= value >> (64 - offset)
    return [word - (1 << 64) if word >= (1 << 63) else word for word in words]


def _litematic_palette(tag: object) -> PyList[BlockState]:
    """Convert a Litematica BlockStatePalette list to internal block states."""

    if not isinstance(tag, (list, List)) or not tag:
        raise ConversionError("Litematic region does not contain a BlockStatePalette list.")
    palette: PyList[BlockState] = []
    for number, entry in enumerate(tag):
        if not isinstance(entry, Compound) or "Name" not in entry:
            raise ConversionError(f"Invalid BlockStatePalette entry #{number}.")
        raw_properties = entry.get("Properties")
        properties = (
            {str(key): str(value) for key, value in raw_properties.items()}
            if isinstance(raw_properties, Compound)
            else {}
        )
        palette.append(make_block_state(str(entry["Name"]), properties))
    return palette


def load_litematic(path: Union[str, Path], progress: ProgressCallback = None) -> StructureData:
    """Load all regions from a Litematica file into one normalized structure."""

    source = Path(path)
    if not source.is_file():
        raise ConversionError(f"File not found: {source}")
    if source.suffix.lower() != ".litematic":
        raise ConversionError("Expected a file with the .litematic extension.")
    _progress(progress, 3, "Opening Litematic NBT...")
    root = _load_root(source)
    regions_tag = root.get("Regions")
    if not isinstance(regions_tag, Compound) or not regions_tag:
        raise ConversionError("Litematic file does not contain any regions.")

    region_specs = []
    global_min = [2**31 - 1, 2**31 - 1, 2**31 - 1]
    global_max = [-(2**31), -(2**31), -(2**31)]
    for region_name, region in regions_tag.items():
        if not isinstance(region, Compound):
            continue
        position = _xyz_compound(region.get("Position"), f"Position in region {region_name}")
        signed_size = _xyz_compound(region.get("Size"), f"Size in region {region_name}")
        if any(value == 0 for value in signed_size):
            raise ConversionError(f"Region {region_name} has a zero-sized axis.")
        size = tuple(abs(value) for value in signed_size)
        for axis in range(3):
            if signed_size[axis] > 0:
                low, high = position[axis], position[axis] + signed_size[axis] - 1
            else:
                low, high = position[axis] + signed_size[axis] + 1, position[axis]
            global_min[axis] = min(global_min[axis], low)
            global_max[axis] = max(global_max[axis], high)
        region_specs.append((str(region_name), region, position, signed_size, size))
    if not region_specs:
        raise ConversionError("Litematic file contains no readable regions.")

    width, height, length = (
        global_max[0] - global_min[0] + 1,
        global_max[1] - global_min[1] + 1,
        global_max[2] - global_min[2] + 1,
    )
    air = make_block_state("minecraft:air")
    blocks = [air] * (width * height * length)
    block_entities: PyList[BlockEntityData] = []
    entities: PyList[EntityData] = []
    region_count = len(region_specs)

    for region_number, (region_name, region, position, signed_size, size) in enumerate(region_specs):
        rw, rh, rl = size
        volume = rw * rh * rl
        palette = _litematic_palette(region.get("BlockStatePalette"))
        bits = max(2, (len(palette) - 1).bit_length())
        raw_states = region.get("BlockStates")
        if not isinstance(raw_states, LongArray):
            raise ConversionError(f"Region {region_name} does not contain a LongArray BlockStates tag.")
        indices = _unpack_litematic_indices(raw_states, volume, bits)

        def storage_to_global(local: Sequence[Union[int, float]]) -> Tuple[Union[int, float], ...]:
            """Map packed-array coordinates to schematic coordinates."""

            return tuple(
                position[axis] + local[axis]
                if signed_size[axis] > 0
                else position[axis] + signed_size[axis] + 1 + local[axis]
                for axis in range(3)
            )

        def region_to_global(relative: Sequence[Union[int, float]]) -> Tuple[Union[int, float], ...]:
            """Entities store signed coordinates in the region coordinate system."""

            return tuple(position[axis] + relative[axis] for axis in range(3))

        for local_index, palette_index in enumerate(indices):
            if palette_index >= len(palette):
                raise ConversionError(
                    f"Region {region_name} references palette index {palette_index}, "
                    f"but its palette has {len(palette)} entries."
                )
            lx = local_index % rw
            local_yz = local_index // rw
            lz = local_yz % rl
            ly = local_yz // rl
            gx, gy, gz = storage_to_global((lx, ly, lz))
            nx, ny, nz = int(gx) - global_min[0], int(gy) - global_min[1], int(gz) - global_min[2]
            blocks[(ny * length + nz) * width + nx] = palette[palette_index]

        for item in _read_block_entities(region.get("TileEntities", region.get("BlockEntities"))):
            raw_global = region_to_global(item.pos)
            normalized = tuple(int(raw_global[axis]) - global_min[axis] for axis in range(3))
            block_entities.append(BlockEntityData(normalized, item.nbt))

        for item in _read_entities(region.get("Entities")):
            raw_pos = region_to_global(item.pos)
            raw_block = region_to_global(item.block_pos)
            normalized_pos = tuple(float(raw_pos[axis]) - global_min[axis] for axis in range(3))
            normalized_block = tuple(int(raw_block[axis]) - global_min[axis] for axis in range(3))
            entities.append(EntityData(normalized_pos, normalized_block, item.nbt))
        _progress(progress, 10 + int((region_number + 1) / region_count * 48), "Reading Litematic regions...")

    structure = StructureData(
        width, height, length, blocks, block_entities, entities,
        int(root.get("MinecraftDataVersion", root.get("DataVersion", DEFAULT_DATA_VERSION))),
        f"Litematica ({region_count} region{'s' if region_count != 1 else ''})",
    )
    structure.validate()
    _progress(progress, 60, "Litematic loaded")
    return structure


def load_structure_file(path: Union[str, Path], progress: ProgressCallback = None) -> StructureData:
    """Load any structure format supported by the application."""

    suffix = Path(path).suffix.lower()
    if suffix == ".litematic":
        return load_litematic(path, progress)
    if suffix == ".nbt":
        return load_structure_nbt(path, progress)
    if suffix in (".schematic", ".schem"):
        return load_schematic(path, progress)
    raise ConversionError(f"Unsupported input format: {suffix or '(no extension)' }.")


def extract_region(
    structure: StructureData,
    first: Sequence[int],
    second: Sequence[int],
) -> StructureData:
    """Return an inclusive cuboid selection translated to a local 0,0,0 origin."""

    if len(first) != 3 or len(second) != 3:
        raise ConversionError("A region requires two x/y/z coordinates.")
    low = tuple(min(int(first[axis]), int(second[axis])) for axis in range(3))
    high = tuple(max(int(first[axis]), int(second[axis])) for axis in range(3))
    bounds = (structure.width, structure.height, structure.length)
    if any(low[axis] < 0 or high[axis] >= bounds[axis] for axis in range(3)):
        raise ConversionError(
            f"Selection {low}..{high} is outside structure bounds "
            f"0..({structure.width - 1}, {structure.height - 1}, {structure.length - 1})."
        )
    width, height, length = (high[axis] - low[axis] + 1 for axis in range(3))
    blocks: PyList[BlockState] = []
    for y in range(low[1], high[1] + 1):
        for z in range(low[2], high[2] + 1):
            for x in range(low[0], high[0] + 1):
                blocks.append(structure.blocks[structure.index(x, y, z)])
    block_entities = [
        BlockEntityData(tuple(item.pos[axis] - low[axis] for axis in range(3)), _deep_compound(item.nbt))
        for item in structure.block_entities
        if all(low[axis] <= item.pos[axis] <= high[axis] for axis in range(3))
    ]
    entities = [
        EntityData(
            tuple(item.pos[axis] - low[axis] for axis in range(3)),
            tuple(item.block_pos[axis] - low[axis] for axis in range(3)),
            _deep_compound(item.nbt),
        )
        for item in structure.entities
        if all(low[axis] <= item.block_pos[axis] <= high[axis] for axis in range(3))
    ]
    result = StructureData(
        width, height, length, blocks, block_entities, entities,
        structure.data_version, f"Selection from {structure.source_format}", list(structure.warnings),
    )
    result.validate()
    return result


def replace_blocks(structure: StructureData, source: str, target: str) -> Tuple[StructureData, int]:
    """Заменяет состояния блоков и возвращает новую структуру и число замен."""

    source_state = parse_block_state(source)
    target_state = parse_block_state(target)
    count = 0
    blocks: PyList[BlockState] = []
    for block in structure.blocks:
        if state_matches(block, source_state):
            blocks.append(target_state)
            count += 1
        else:
            blocks.append(block)
    return replace(structure, blocks=blocks), count


def _rotate_discrete(pos: Sequence[int], width: int, length: int) -> Tuple[int, int, int]:
    x, y, z = pos
    return length - 1 - z, y, x


def _rotate_exact(pos: Sequence[float], width: int, length: int) -> Tuple[float, float, float]:
    x, y, z = pos
    return length - z, y, x


def rotate_structure(structure: StructureData, degrees: int) -> StructureData:
    """Поворачивает структуру вокруг оси Y по часовой стрелке."""

    if degrees not in (0, 90, 180, 270):
        raise ConversionError("Поворот должен быть 0, 90, 180 или 270 градусов.")
    turns = degrees // 90
    result = structure
    for _ in range(turns):
        old_width, old_length = result.width, result.length
        new_width, new_length = old_length, old_width
        new_blocks = [make_block_state("minecraft:air")] * result.volume
        for y in range(result.height):
            for z in range(old_length):
                for x in range(old_width):
                    old_index = (y * old_length + z) * old_width + x
                    nx, ny, nz = _rotate_discrete((x, y, z), old_width, old_length)
                    new_index = (ny * new_length + nz) * new_width + nx
                    new_blocks[new_index] = rotate_block_state(result.blocks[old_index], 1)
        new_block_entities = [
            BlockEntityData(_rotate_discrete(item.pos, old_width, old_length), _deep_compound(item.nbt))
            for item in result.block_entities
        ]
        new_entities = [
            EntityData(
                _rotate_exact(item.pos, old_width, old_length),
                _rotate_discrete(item.block_pos, old_width, old_length),
                _deep_compound(item.nbt),
            )
            for item in result.entities
        ]
        result = replace(
            result, width=new_width, length=new_length, blocks=new_blocks,
            block_entities=new_block_entities, entities=new_entities,
        )
    result.validate()
    return result


def _palette_entry(block: BlockState) -> Compound:
    entry = Compound({"Name": String(block.name)})
    if block.properties:
        entry["Properties"] = Compound({key: String(value) for key, value in block.properties})
    return entry


def save_structure_nbt(structure: StructureData, path: Union[str, Path], progress: ProgressCallback = None) -> Path:
    """Сохраняет единое представление в Java Structure NBT (gzip, big-endian)."""

    structure.validate()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    palette = structure.palette
    palette_ids = {block: index for index, block in enumerate(palette)}
    entities_by_pos = {item.pos: item for item in structure.block_entities}
    block_entries: PyList[Compound] = []
    volume = structure.volume
    for y in range(structure.height):
        for z in range(structure.length):
            for x in range(structure.width):
                index = structure.index(x, y, z)
                entry = Compound({
                    "state": Int(palette_ids[structure.blocks[index]]),
                    "pos": List[Int]([Int(x), Int(y), Int(z)]),
                })
                block_entity = entities_by_pos.get((x, y, z))
                if block_entity:
                    entry["nbt"] = _deep_compound(block_entity.nbt)
                block_entries.append(entry)
                if index and index % max(1, volume // 20) == 0:
                    _progress(progress, 65 + int(index / volume * 25), "Формирование Structure NBT…")

    entity_entries = []
    for entity in structure.entities:
        entity_entries.append(Compound({
            "pos": List[Double]([Double(value) for value in entity.pos]),
            "blockPos": List[Int]([Int(value) for value in entity.block_pos]),
            "nbt": _deep_compound(entity.nbt),
        }))

    root = Compound({
        "DataVersion": Int(structure.data_version or DEFAULT_DATA_VERSION),
        "size": List[Int]([Int(structure.width), Int(structure.height), Int(structure.length)]),
        "palette": List[Compound]([_palette_entry(block) for block in palette]),
        "blocks": List[Compound](block_entries),
        "entities": List[Compound](entity_entries),
    })
    try:
        File({"": root}, gzipped=True).save(str(destination))
    except OSError as exc:
        raise ConversionError(f"Не удалось сохранить файл: {exc}") from exc
    _progress(progress, 100, "Готово")
    return destination


def save_sponge_schematic(structure: StructureData, path: Union[str, Path], progress: ProgressCallback = None) -> Path:
    """Сохраняет структуру как Sponge Schematic v2 с VarInt BlockData."""

    structure.validate()
    if max(structure.width, structure.height, structure.length) > 32767:
        raise ConversionError("Sponge v2 не поддерживает размер стороны больше 32767 блоков.")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    palette = structure.palette
    palette_ids = {block: index for index, block in enumerate(palette)}
    indices = [palette_ids[block] for block in structure.blocks]

    block_entities = []
    for item in structure.block_entities:
        data = _deep_compound(item.nbt)
        data["Pos"] = IntArray(item.pos)
        if "id" in data and "Id" not in data:
            data["Id"] = String(str(data.pop("id")))
        block_entities.append(data)
    entities = []
    for item in structure.entities:
        data = _deep_compound(item.nbt)
        data["Pos"] = List[Double]([Double(value) for value in item.pos])
        entities.append(data)

    root = Compound({
        "Version": Int(2),
        "DataVersion": Int(structure.data_version or DEFAULT_DATA_VERSION),
        "Width": Short(structure.width),
        "Height": Short(structure.height),
        "Length": Short(structure.length),
        "PaletteMax": Int(len(palette)),
        "Palette": Compound({block.as_string(): Int(index) for block, index in palette_ids.items()}),
        "BlockData": ByteArray(_encode_varints(indices)),
        "BlockEntities": List[Compound](block_entities),
        "Entities": List[Compound](entities),
        "Offset": IntArray([0, 0, 0]),
        "Metadata": Compound(),
    })
    try:
        File({"Schematic": root}, gzipped=True).save(str(destination))
    except OSError as exc:
        raise ConversionError(f"Не удалось сохранить файл: {exc}") from exc
    _progress(progress, 100, "Готово")
    return destination


def save_litematic(
    structure: StructureData,
    path: Union[str, Path],
    progress: ProgressCallback = None,
    name: Optional[str] = None,
    author: str = "Minecraft Structure Forge",
    description: str = "Exported by Minecraft Structure Forge",
) -> Path:
    """Save a structure as a single-region Litematica schematic."""

    structure.validate()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    air = make_block_state("minecraft:air")
    palette = list(structure.palette)
    if air in palette:
        palette.remove(air)
    palette.insert(0, air)
    palette_ids = {block: index for index, block in enumerate(palette)}
    indices = [palette_ids[block] for block in structure.blocks]
    bits = max(2, (len(palette) - 1).bit_length())
    packed = _pack_litematic_indices(indices, bits)

    tile_entities = []
    for item in structure.block_entities:
        data = _deep_compound(item.nbt)
        data["x"], data["y"], data["z"] = (Int(value) for value in item.pos)
        tile_entities.append(data)
    entities = []
    for item in structure.entities:
        data = _deep_compound(item.nbt)
        data["Pos"] = List[Double]([Double(value) for value in item.pos])
        entities.append(data)

    def xyz(x: int, y: int, z: int) -> Compound:
        return Compound({"x": Int(x), "y": Int(y), "z": Int(z)})

    region = Compound({
        "Position": xyz(0, 0, 0),
        "Size": xyz(structure.width, structure.height, structure.length),
        "BlockStatePalette": List[Compound]([_palette_entry(block) for block in palette]),
        "BlockStates": LongArray(packed),
        "Entities": List[Compound](entities),
        "TileEntities": List[Compound](tile_entities),
        "PendingBlockTicks": List[Compound]([]),
        "PendingFluidTicks": List[Compound]([]),
    })
    now_ms = int(time.time() * 1000)
    display_name = name or destination.stem or "Structure"
    total_blocks = sum(1 for block in structure.blocks if block.name not in {
        "minecraft:air", "minecraft:cave_air", "minecraft:void_air", "minecraft:structure_void"
    })
    metadata = Compound({
        "Name": String(display_name),
        "Author": String(author),
        "Description": String(description),
        "RegionCount": Int(1),
        "TimeCreated": Long(now_ms),
        "TimeModified": Long(now_ms),
        "TotalBlocks": Int(total_blocks),
        "TotalVolume": Int(structure.volume),
        "EnclosingSize": xyz(structure.width, structure.height, structure.length),
    })
    root = Compound({
        "Version": Int(6),
        "SubVersion": Int(1),
        "MinecraftDataVersion": Int(structure.data_version or DEFAULT_DATA_VERSION),
        "Metadata": metadata,
        "Regions": Compound({display_name: region}),
    })
    _progress(progress, 88, "Writing Litematic...")
    try:
        # nbtlib 1.x expects a mapping from the root name to the root compound.
        File({"": root}, gzipped=True).save(str(destination))
    except (OSError, TypeError, ValueError) as exc:
        raise ConversionError(f"Could not save Litematic file: {exc}") from exc
    _progress(progress, 100, "Done")
    return destination


def save_structure_file(
    structure: StructureData,
    path: Union[str, Path],
    progress: ProgressCallback = None,
    texture_pack: Optional[Union[str, Path]] = None,
) -> Path:
    """Save a structure according to the destination extension."""

    destination = Path(path)
    suffix = destination.suffix.lower()
    if suffix == ".nbt":
        return save_structure_nbt(structure, destination, progress)
    if suffix in (".schematic", ".schem"):
        return save_sponge_schematic(structure, destination, progress)
    if suffix == ".litematic":
        return save_litematic(structure, destination, progress)
    if suffix in (".stl", ".obj"):
        from mesh_export import export_obj, export_stl

        if suffix == ".stl":
            return export_stl(structure, destination, progress=progress)
        return export_obj(structure, destination, texture_pack=texture_pack, progress=progress)
    raise ConversionError(f"Unsupported output format: {suffix or '(no extension)'}.")


def convert_file(
    source: Union[str, Path],
    destination: Union[str, Path],
    replacement: Optional[Tuple[str, str]] = None,
    rotation: int = 0,
    progress: ProgressCallback = None,
    region: Optional[Tuple[Sequence[int], Sequence[int]]] = None,
    texture_pack: Optional[Union[str, Path]] = None,
) -> Tuple[Path, StructureData, int]:
    """Convert, transform and optionally crop any supported structure format."""

    source_path = Path(source)
    destination_path = Path(destination)
    structure = load_structure_file(source_path, progress)

    replacements = 0
    if replacement:
        _progress(progress, 62, "Замена блоков…")
        structure, replacements = replace_blocks(structure, replacement[0], replacement[1])
    if rotation:
        _progress(progress, 64, f"Поворот на {rotation}°…")
        structure = rotate_structure(structure, rotation)
    if region:
        _progress(progress, 66, "Cropping selected region...")
        structure = extract_region(structure, region[0], region[1])
    result = save_structure_file(structure, destination_path, progress, texture_pack)
    return result, structure, replacements


def build_preview_map(structure: StructureData) -> PreviewMap:
    """Строит карту верхних блоков с высотным затенением.

    Изображение хранит один пиксель на блок. GUI масштабирует его алгоритмом
    NEAREST, поэтому контуры остаются резкими при любом приближении.
    """

    try:
        from PIL import Image
    except ImportError as exc:
        raise ConversionError("Для превью установите Pillow: pip install Pillow") from exc

    air_names = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air", "minecraft:structure_void"}
    image = Image.new("RGB", (structure.width, structure.length), "#18202b")
    pixels = image.load()
    top_blocks: PyList[Optional[BlockState]] = []
    heights: PyList[int] = []
    for z in range(structure.length):
        for x in range(structure.width):
            top_block: Optional[BlockState] = None
            top_y = -1
            for y in range(structure.height - 1, -1, -1):
                block = structure.blocks[structure.index(x, y, z)]
                if block.name not in air_names:
                    top_block = block
                    top_y = y
                    base = tuple(int(block_color(block)[offset:offset + 2], 16) for offset in (1, 3, 5))
                    # Высокие блоки немного светлее, а шахматный микроконтраст
                    # помогает визуально отделять соседние клетки без сетки.
                    height_factor = 0.72 + 0.28 * ((y + 1) / max(1, structure.height))
                    texture_factor = 0.96 if (x + z) % 2 else 1.0
                    pixels[x, z] = tuple(min(255, int(channel * height_factor * texture_factor)) for channel in base)
                    break

            top_blocks.append(top_block)
            heights.append(top_y)

    return PreviewMap(image, structure.width, structure.length, tuple(top_blocks), tuple(heights))


def build_3d_render_model(
    structure: StructureData,
    large_threshold: int = 10000,
    max_blocks: int = 5000,
) -> RenderModel3D:
    """Подготавливает цветные кубы для отдельного OpenGL-окна.

    При большой постройке выбирается равномерная выборка по всему массиву,
    а не только нижние первые слои. Это сохраняет общий силуэт и ограничивает
    объём геометрии, передаваемой видеокарте.
    """

    structure.validate()
    if large_threshold <= 0 or max_blocks <= 0:
        raise ConversionError("Лимиты 3D-предпросмотра должны быть больше нуля.")
    air_names = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air", "minecraft:structure_void"}
    total_blocks = sum(1 for block in structure.blocks if block.name not in air_names)
    simplified = total_blocks > large_threshold
    target_count = min(total_blocks, max_blocks) if simplified else total_blocks
    if target_count == 0:
        return RenderModel3D((), 0, False, structure.width, structure.height, structure.length)

    stride = total_blocks / target_count
    next_pick = 0.0
    solid_index = 0
    selected: PyList[RenderBlock3D] = []
    for index, block in enumerate(structure.blocks):
        if block.name in air_names:
            continue
        if not simplified or solid_index + 1 > next_pick:
            x = index % structure.width
            yz = index // structure.width
            z = yz % structure.length
            y = yz // structure.length
            color_hex = block_color(block)
            color = tuple(int(color_hex[offset:offset + 2], 16) / 255.0 for offset in (1, 3, 5))
            selected.append(RenderBlock3D(x, y, z, color))
            next_pick += stride
            if len(selected) >= target_count:
                break
        solid_index += 1

    return RenderModel3D(
        tuple(selected), total_blocks, simplified,
        structure.width, structure.height, structure.length,
    )


def render_preview(structure: StructureData, max_size: int = 360):
    """Создаёт статичное Pillow Image; сохранено для внешних вызовов API."""

    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise ConversionError("Для превью установите Pillow: pip install Pillow") from exc

    preview = build_preview_map(structure)
    image = preview.image

    scale = min(max_size / max(1, structure.width), max_size / max(1, structure.length))
    new_size = (max(1, int(structure.width * scale)), max(1, int(structure.length * scale)))
    image = image.resize(new_size, Image.Resampling.NEAREST)
    framed = Image.new("RGB", (max_size, max_size), "#101720")
    framed.paste(image, ((max_size - image.width) // 2, (max_size - image.height) // 2))
    draw = ImageDraw.Draw(framed)
    draw.rectangle((0, 0, max_size - 1, max_size - 1), outline="#293647", width=2)
    return framed
