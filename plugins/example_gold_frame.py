"""Example Minecraft Structure Forge plugin.

The plugin replaces exposed stone blocks with gold blocks. Copy this file and
change ``process`` to create custom generators or replacement rules.
"""

PLUGIN_NAME = "Example: golden surface"
PLUGIN_DESCRIPTION = "Replaces exposed stone blocks with gold blocks without changing the structure size."


def process(structure, api):
    stone = api["make_block_state"]("minecraft:stone")
    gold = api["make_block_state"]("minecraft:gold_block")
    air_names = api["air_names"]
    original = list(structure.blocks)

    for y in range(structure.height):
        for z in range(structure.length):
            for x in range(structure.width):
                index = structure.index(x, y, z)
                if original[index] != stone:
                    continue
                exposed = False
                for dx, dy, dz in ((-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1)):
                    nx, ny, nz = x + dx, y + dy, z + dz
                    if not (0 <= nx < structure.width and 0 <= ny < structure.height and 0 <= nz < structure.length):
                        exposed = True
                        break
                    if original[structure.index(nx, ny, nz)].name in air_names:
                        exposed = True
                        break
                if exposed:
                    structure.blocks[index] = gold
    return structure

