"""Surface-only STL and textured OBJ exporters for Minecraft structures."""

from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple, Union

from advanced import AIR_NAMES, TextureCache
from converter import ConversionError, ProgressCallback, StructureData
from utils import BlockState


# Each face contains its neighbor offset, outward normal and four local corners.
FACES = (
    ((-1, 0, 0), (-1.0, 0.0, 0.0), ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0))),
    ((1, 0, 0), (1.0, 0.0, 0.0), ((1, 0, 1), (1, 0, 0), (1, 1, 0), (1, 1, 1))),
    ((0, -1, 0), (0.0, -1.0, 0.0), ((0, 0, 1), (0, 0, 0), (1, 0, 0), (1, 0, 1))),
    ((0, 1, 0), (0.0, 1.0, 0.0), ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0))),
    ((0, 0, -1), (0.0, 0.0, -1.0), ((1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0))),
    ((0, 0, 1), (0.0, 0.0, 1.0), ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))),
)


def _solid(structure: StructureData, x: int, y: int, z: int) -> bool:
    if not (0 <= x < structure.width and 0 <= y < structure.height and 0 <= z < structure.length):
        return False
    return structure.blocks[structure.index(x, y, z)].name not in AIR_NAMES


def iter_surface_faces(structure: StructureData):
    """Yield only faces touching air or the outside of the structure."""

    for y in range(structure.height):
        for z in range(structure.length):
            for x in range(structure.width):
                state = structure.blocks[structure.index(x, y, z)]
                if state.name in AIR_NAMES:
                    continue
                for neighbor, normal, corners in FACES:
                    nx, ny, nz = x + neighbor[0], y + neighbor[1], z + neighbor[2]
                    if not _solid(structure, nx, ny, nz):
                        vertices = tuple((x + cx, y + cy, z + cz) for cx, cy, cz in corners)
                        yield state, normal, vertices


def export_stl(
    structure: StructureData,
    path: Union[str, Path],
    scale_mm: float = 1.0,
    progress: ProgressCallback = None,
) -> Path:
    """Export a watertight-looking surface as a compact binary STL mesh."""

    structure.validate()
    if scale_mm <= 0:
        raise ConversionError("STL scale must be greater than zero.")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    faces = list(iter_surface_faces(structure))
    triangle_count = len(faces) * 2
    if triangle_count > 0xFFFFFFFF:
        raise ConversionError("The STL mesh contains too many triangles.")
    header = b"Minecraft Structure Forge binary STL"[:80].ljust(80, b"\0")
    try:
        with destination.open("wb") as stream:
            stream.write(header)
            stream.write(struct.pack("<I", triangle_count))
            for number, (_, normal, vertices) in enumerate(faces):
                scaled = [tuple(float(value) * scale_mm for value in vertex) for vertex in vertices]
                for indices in ((0, 1, 2), (0, 2, 3)):
                    values = list(normal)
                    for index in indices:
                        values.extend(scaled[index])
                    stream.write(struct.pack("<12fH", *values, 0))
                if progress and number % max(1, len(faces) // 20) == 0:
                    progress(70 + int(number / max(1, len(faces)) * 28), "Writing STL surface...")
    except OSError as exc:
        raise ConversionError(f"Could not save STL file: {exc}") from exc
    if progress:
        progress(100, "Done")
    return destination


def _create_atlas(states: Sequence[BlockState], texture_pack: Optional[Union[str, Path]], path: Path):
    try:
        from PIL import Image
    except ImportError as exc:
        raise ConversionError("Pillow is required for textured OBJ export.") from exc
    tile_size = 16
    columns = max(1, math.ceil(math.sqrt(len(states))))
    rows = max(1, math.ceil(len(states) / columns))
    atlas = Image.new("RGBA", (columns * tile_size, rows * tile_size), (255, 0, 255, 255))
    cache = TextureCache(texture_pack, tile_size)
    uv = {}
    for index, state in enumerate(states):
        column, row = index % columns, index // columns
        atlas.paste(cache.image(state), (column * tile_size, row * tile_size))
        # OBJ UV coordinates start at the bottom-left, unlike Pillow images.
        u0, u1 = column / columns, (column + 1) / columns
        v1, v0 = 1.0 - row / rows, 1.0 - (row + 1) / rows
        uv[state] = ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
    path.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(str(path), format="PNG", optimize=True)
    return uv


def export_obj(
    structure: StructureData,
    path: Union[str, Path],
    texture_pack: Optional[Union[str, Path]] = None,
    progress: ProgressCallback = None,
) -> Path:
    """Export an OBJ, MTL and PNG atlas that can be imported directly into Blender."""

    structure.validate()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    faces = list(iter_surface_faces(structure))
    states = list(dict.fromkeys(face[0] for face in faces))
    if not states:
        states = [structure.blocks[0]]
    texture_folder = destination.parent / f"{destination.stem}_textures"
    atlas_path = texture_folder / "atlas.png"
    uv_by_state = _create_atlas(states, texture_pack, atlas_path)
    material_path = destination.with_suffix(".mtl")
    material_text = "\n".join((
        "# Generated by Minecraft Structure Forge",
        "newmtl blocks",
        "Ka 0.180000 0.180000 0.180000",
        "Kd 1.000000 1.000000 1.000000",
        "Ks 0.000000 0.000000 0.000000",
        "d 1.0",
        "illum 1",
        f"map_Kd {texture_folder.name}/atlas.png",
        "",
    ))

    lines: List[str] = [
        "# Generated by Minecraft Structure Forge",
        f"mtllib {material_path.name}",
        "o MinecraftStructure",
        "usemtl blocks",
    ]
    vertex_index = 1
    texture_index = 1
    for number, (state, normal, vertices) in enumerate(faces):
        for vertex in vertices:
            lines.append(f"v {vertex[0]:.6f} {vertex[1]:.6f} {vertex[2]:.6f}")
        for u, v in uv_by_state[state]:
            lines.append(f"vt {u:.8f} {v:.8f}")
        lines.append(f"vn {normal[0]:.1f} {normal[1]:.1f} {normal[2]:.1f}")
        normal_index = number + 1
        refs = [f"{vertex_index + offset}/{texture_index + offset}/{normal_index}" for offset in range(4)]
        lines.append(f"f {refs[0]} {refs[1]} {refs[2]}")
        lines.append(f"f {refs[0]} {refs[2]} {refs[3]}")
        vertex_index += 4
        texture_index += 4
        if progress and number % max(1, len(faces) // 20) == 0:
            progress(70 + int(number / max(1, len(faces)) * 28), "Writing textured OBJ...")
    try:
        material_path.write_text(material_text, encoding="utf-8")
        destination.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    except OSError as exc:
        raise ConversionError(f"Could not save OBJ files: {exc}") from exc
    if progress:
        progress(100, "Done")
    return destination

