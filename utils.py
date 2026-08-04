"""Вспомогательные функции для работы с блоками Minecraft.

Модуль не зависит от tkinter, поэтому его можно использовать отдельно от GUI.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional, Tuple


_BLOCK_RE = re.compile(r"^\s*([a-z0-9_.-]+(?::[a-z0-9_./-]+)?)(?:\[([^]]*)\])?\s*$", re.I)


@dataclass(frozen=True)
class BlockState:
    """Имя блока и отсортированный набор его свойств."""

    name: str
    properties: Tuple[Tuple[str, str], ...] = ()

    @property
    def props(self) -> Dict[str, str]:
        return dict(self.properties)

    def as_string(self) -> str:
        if not self.properties:
            return self.name
        values = ",".join(f"{key}={value}" for key, value in self.properties)
        return f"{self.name}[{values}]"


def make_block_state(name: str, properties: Optional[Mapping[str, object]] = None) -> BlockState:
    """Создаёт нормализованное состояние блока."""

    clean_name = str(name).strip().lower()
    if ":" not in clean_name:
        clean_name = f"minecraft:{clean_name}"
    clean_properties = tuple(
        sorted((str(key).strip().lower(), str(value).strip().lower()) for key, value in (properties or {}).items())
    )
    return BlockState(clean_name, clean_properties)


def parse_block_state(value: str) -> BlockState:
    """Разбирает строку вида ``minecraft:oak_stairs[facing=north]``."""

    match = _BLOCK_RE.match(value or "")
    if not match:
        raise ValueError("Блок должен иметь вид minecraft:stone или minecraft:stairs[facing=north]")
    name, raw_properties = match.groups()
    properties: Dict[str, str] = {}
    if raw_properties:
        for item in raw_properties.split(","):
            if "=" not in item:
                raise ValueError(f"Неверное свойство блока: {item!r}")
            key, prop_value = item.split("=", 1)
            key, prop_value = key.strip(), prop_value.strip()
            if not key or not prop_value:
                raise ValueError(f"Неверное свойство блока: {item!r}")
            properties[key] = prop_value
    return make_block_state(name, properties)


def state_matches(block: BlockState, pattern: BlockState) -> bool:
    """Сопоставляет блок по имени, а при наличии свойств — и по свойствам."""

    return block.name == pattern.name and (not pattern.properties or block == pattern)


# Числовые ID использовались в классическом формате MCEdit до Minecraft 1.13.
# Для специальных вариантов ниже учитывается поле Data; неизвестный ID заменяется
# барьером, чтобы потеря данных была видна в игре, а не проходила незаметно.
LEGACY_NAMES: Dict[int, str] = {
    0: "air", 1: "stone", 2: "grass_block", 3: "dirt", 4: "cobblestone",
    5: "oak_planks", 6: "oak_sapling", 7: "bedrock", 8: "water", 9: "water",
    10: "lava", 11: "lava", 12: "sand", 13: "gravel", 14: "gold_ore",
    15: "iron_ore", 16: "coal_ore", 17: "oak_log", 18: "oak_leaves", 19: "sponge",
    20: "glass", 21: "lapis_ore", 22: "lapis_block", 23: "dispenser",
    24: "sandstone", 25: "note_block", 26: "red_bed", 27: "powered_rail",
    28: "detector_rail", 29: "sticky_piston", 30: "cobweb", 31: "short_grass",
    32: "dead_bush", 33: "piston", 34: "piston_head", 35: "white_wool",
    37: "dandelion", 38: "poppy", 39: "brown_mushroom", 40: "red_mushroom",
    41: "gold_block", 42: "iron_block", 43: "smooth_stone", 44: "smooth_stone_slab",
    45: "bricks", 46: "tnt", 47: "bookshelf", 48: "mossy_cobblestone",
    49: "obsidian", 50: "torch", 51: "fire", 52: "spawner", 53: "oak_stairs",
    54: "chest", 55: "redstone_wire", 56: "diamond_ore", 57: "diamond_block",
    58: "crafting_table", 59: "wheat", 60: "farmland", 61: "furnace",
    62: "furnace", 63: "oak_sign", 64: "oak_door", 65: "ladder", 66: "rail",
    67: "cobblestone_stairs", 68: "oak_wall_sign", 69: "lever",
    70: "stone_pressure_plate", 71: "iron_door", 72: "oak_pressure_plate",
    73: "redstone_ore", 74: "redstone_ore", 75: "redstone_wall_torch",
    76: "redstone_torch", 77: "stone_button", 78: "snow", 79: "ice",
    80: "snow_block", 81: "cactus", 82: "clay", 83: "sugar_cane", 84: "jukebox",
    85: "oak_fence", 86: "carved_pumpkin", 87: "netherrack", 88: "soul_sand",
    89: "glowstone", 90: "nether_portal", 91: "jack_o_lantern", 92: "cake",
    93: "repeater", 94: "repeater", 95: "white_stained_glass", 96: "oak_trapdoor",
    97: "infested_stone", 98: "stone_bricks", 99: "brown_mushroom_block",
    100: "red_mushroom_block", 101: "iron_bars", 102: "glass_pane", 103: "melon",
    104: "pumpkin_stem", 105: "melon_stem", 106: "vine", 107: "oak_fence_gate",
    108: "brick_stairs", 109: "stone_brick_stairs", 110: "mycelium",
    111: "lily_pad", 112: "nether_bricks", 113: "nether_brick_fence",
    114: "nether_brick_stairs", 115: "nether_wart", 116: "enchanting_table",
    117: "brewing_stand", 118: "cauldron", 119: "end_portal", 120: "end_portal_frame",
    121: "end_stone", 122: "dragon_egg", 123: "redstone_lamp", 124: "redstone_lamp",
    125: "oak_planks", 126: "oak_slab", 127: "cocoa", 128: "sandstone_stairs",
    129: "emerald_ore", 130: "ender_chest", 131: "tripwire_hook", 132: "tripwire",
    133: "emerald_block", 134: "spruce_stairs", 135: "birch_stairs",
    136: "jungle_stairs", 137: "command_block", 138: "beacon",
    139: "cobblestone_wall", 140: "flower_pot", 141: "carrots", 142: "potatoes",
    143: "oak_button", 144: "skeleton_skull", 145: "anvil", 146: "trapped_chest",
    147: "light_weighted_pressure_plate", 148: "heavy_weighted_pressure_plate",
    149: "comparator", 150: "comparator", 151: "daylight_detector",
    152: "redstone_block", 153: "nether_quartz_ore", 154: "hopper",
    155: "quartz_block", 156: "quartz_stairs", 157: "activator_rail", 158: "dropper",
    159: "white_terracotta", 160: "white_stained_glass_pane", 161: "acacia_leaves",
    162: "acacia_log", 163: "acacia_stairs", 164: "dark_oak_stairs",
    165: "slime_block", 166: "barrier", 167: "iron_trapdoor", 168: "prismarine",
    169: "sea_lantern", 170: "hay_block", 171: "white_carpet", 172: "terracotta",
    173: "coal_block", 174: "packed_ice", 175: "sunflower", 176: "white_banner",
    177: "white_wall_banner", 178: "daylight_detector", 179: "red_sandstone",
    180: "red_sandstone_stairs", 181: "red_sandstone", 182: "red_sandstone_slab",
    183: "spruce_fence_gate", 184: "birch_fence_gate", 185: "jungle_fence_gate",
    186: "dark_oak_fence_gate", 187: "acacia_fence_gate", 188: "spruce_fence",
    189: "birch_fence", 190: "jungle_fence", 191: "dark_oak_fence",
    192: "acacia_fence", 193: "spruce_door", 194: "birch_door", 195: "jungle_door",
    196: "acacia_door", 197: "dark_oak_door", 198: "end_rod", 199: "chorus_plant",
    200: "chorus_flower", 201: "purpur_block", 202: "purpur_pillar",
    203: "purpur_stairs", 204: "purpur_block", 205: "purpur_slab",
    206: "end_stone_bricks", 207: "beetroots", 208: "dirt_path", 209: "end_gateway",
    210: "repeating_command_block", 211: "chain_command_block", 212: "frosted_ice",
    213: "magma_block", 214: "nether_wart_block", 215: "red_nether_bricks",
    216: "bone_block", 217: "structure_void", 218: "observer", 219: "white_shulker_box",
    220: "orange_shulker_box", 221: "magenta_shulker_box", 222: "light_blue_shulker_box",
    223: "yellow_shulker_box", 224: "lime_shulker_box", 225: "pink_shulker_box",
    226: "gray_shulker_box", 227: "light_gray_shulker_box", 228: "cyan_shulker_box",
    229: "purple_shulker_box", 230: "blue_shulker_box", 231: "brown_shulker_box",
    232: "green_shulker_box", 233: "red_shulker_box", 234: "black_shulker_box",
    235: "white_glazed_terracotta", 236: "orange_glazed_terracotta",
    237: "magenta_glazed_terracotta", 238: "light_blue_glazed_terracotta",
    239: "yellow_glazed_terracotta", 240: "lime_glazed_terracotta",
    241: "pink_glazed_terracotta", 242: "gray_glazed_terracotta",
    243: "light_gray_glazed_terracotta", 244: "cyan_glazed_terracotta",
    245: "purple_glazed_terracotta", 246: "blue_glazed_terracotta",
    247: "brown_glazed_terracotta", 248: "green_glazed_terracotta",
    249: "red_glazed_terracotta", 250: "black_glazed_terracotta",
    251: "white_concrete", 252: "white_concrete_powder", 255: "structure_block",
}

COLORS = (
    "white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray",
    "light_gray", "cyan", "purple", "blue", "brown", "green", "red", "black",
)
WOODS = ("oak", "spruce", "birch", "jungle", "acacia", "dark_oak")


def _stairs(name: str, data: int) -> BlockState:
    facings = ("east", "west", "south", "north")
    return make_block_state(name, {"facing": facings[data & 3], "half": "top" if data & 4 else "bottom"})


def legacy_block_state(block_id: int, data: int = 0) -> BlockState:
    """Преобразует классические числовые ID/Data в современный block state."""

    data &= 0xF
    if block_id == 1:
        return make_block_state(("stone", "granite", "polished_granite", "diorite", "polished_diorite", "andesite", "polished_andesite")[min(data, 6)])
    if block_id == 3:
        return make_block_state(("dirt", "coarse_dirt", "podzol")[min(data, 2)])
    if block_id in (5, 6):
        wood = WOODS[min(data & 7, 5)]
        return make_block_state(f"{wood}_{'planks' if block_id == 5 else 'sapling'}")
    if block_id == 12:
        return make_block_state("red_sand" if data == 1 else "sand")
    if block_id in (17, 162):
        wood_list = ("oak", "spruce", "birch", "jungle") if block_id == 17 else ("acacia", "dark_oak")
        wood = wood_list[min(data & 3, len(wood_list) - 1)]
        axis = {0: "y", 4: "x", 8: "z", 12: "y"}[data & 12]
        return make_block_state(f"{wood}_log", {"axis": axis})
    if block_id in (18, 161):
        wood_list = ("oak", "spruce", "birch", "jungle") if block_id == 18 else ("acacia", "dark_oak")
        wood = wood_list[min(data & 3, len(wood_list) - 1)]
        return make_block_state(f"{wood}_leaves", {"persistent": "true" if data & 4 else "false"})
    if block_id == 24:
        return make_block_state(("sandstone", "chiseled_sandstone", "cut_sandstone")[min(data, 2)])
    if block_id in (35, 95, 159, 160, 171, 176, 177, 251, 252):
        suffixes = {
            35: "wool", 95: "stained_glass", 159: "terracotta", 160: "stained_glass_pane",
            171: "carpet", 176: "banner", 177: "wall_banner", 251: "concrete", 252: "concrete_powder",
        }
        return make_block_state(f"{COLORS[data]}_{suffixes[block_id]}")
    if block_id == 38:
        flowers = ("poppy", "blue_orchid", "allium", "azure_bluet", "red_tulip", "orange_tulip", "white_tulip", "pink_tulip", "oxeye_daisy")
        return make_block_state(flowers[min(data, len(flowers) - 1)])
    if block_id in (44, 126):
        slab_names = ("stone", "sandstone", "petrified_oak", "cobblestone", "brick", "stone_brick", "nether_brick", "quartz") if block_id == 44 else WOODS
        material = slab_names[min(data & 7, len(slab_names) - 1)]
        name = f"{material}_slab" if not material.endswith("brick") else f"{material}_slab"
        return make_block_state(name, {"type": "top" if data & 8 else "bottom"})
    if block_id in (53, 67, 108, 109, 114, 128, 134, 135, 136, 156, 163, 164, 180, 203):
        return _stairs(LEGACY_NAMES[block_id], data)
    if block_id in (23, 54, 61, 62, 65, 68, 130, 146, 154, 158):
        facing = {2: "north", 3: "south", 4: "west", 5: "east"}.get(data & 7, "north")
        return make_block_state(LEGACY_NAMES[block_id], {"facing": facing})
    if block_id == 50:
        if data == 5 or data == 0:
            return make_block_state("torch")
        return make_block_state("wall_torch", {"facing": {1: "east", 2: "west", 3: "south", 4: "north"}.get(data, "north")})
    if block_id in (63,):
        return make_block_state("oak_sign", {"rotation": str(data)})
    if block_id in (64, 71, 193, 194, 195, 196, 197):
        if data & 8:
            return make_block_state(LEGACY_NAMES[block_id], {"half": "upper", "hinge": "right" if data & 1 else "left", "powered": "true" if data & 2 else "false"})
        return make_block_state(LEGACY_NAMES[block_id], {"half": "lower", "facing": ("east", "south", "west", "north")[data & 3], "open": "true" if data & 4 else "false"})
    if block_id in (86, 91):
        return make_block_state(LEGACY_NAMES[block_id], {"facing": ("south", "west", "north", "east")[data & 3]})
    if block_id == 98:
        return make_block_state(("stone_bricks", "mossy_stone_bricks", "cracked_stone_bricks", "chiseled_stone_bricks")[min(data, 3)])
    if block_id == 139:
        return make_block_state("mossy_cobblestone_wall" if data == 1 else "cobblestone_wall")
    if block_id == 155:
        names = ("quartz_block", "chiseled_quartz_block", "quartz_pillar")
        state = make_block_state(names[min(data & 3, 2)])
        if (data & 3) == 2:
            return make_block_state(state.name, {"axis": "x" if data == 3 else "z" if data == 4 else "y"})
        return state
    if block_id == 168:
        return make_block_state(("prismarine", "prismarine_bricks", "dark_prismarine")[min(data, 2)])
    if block_id == 175:
        return make_block_state(("sunflower", "lilac", "tall_grass", "large_fern", "rose_bush", "peony")[min(data & 7, 5)], {"half": "upper" if data & 8 else "lower"})

    name = LEGACY_NAMES.get(block_id)
    if name is None:
        return make_block_state("barrier")
    return make_block_state(name)


_FACING_CLOCKWISE = {"north": "east", "east": "south", "south": "west", "west": "north"}
_RAIL_CLOCKWISE = {
    "north_south": "east_west", "east_west": "north_south", "ascending_east": "ascending_south",
    "ascending_south": "ascending_west", "ascending_west": "ascending_north",
    "ascending_north": "ascending_east", "south_east": "south_west", "south_west": "north_west",
    "north_west": "north_east", "north_east": "south_east",
}


def rotate_block_state(block: BlockState, quarter_turns: int) -> BlockState:
    """Поворачивает направленные свойства блока по часовой стрелке."""

    turns = quarter_turns % 4
    properties = block.props
    for _ in range(turns):
        if properties.get("facing") in _FACING_CLOCKWISE:
            properties["facing"] = _FACING_CLOCKWISE[properties["facing"]]
        if properties.get("axis") in ("x", "z"):
            properties["axis"] = "z" if properties["axis"] == "x" else "x"
        if "rotation" in properties:
            try:
                properties["rotation"] = str((int(properties["rotation"]) + 4) % 16)
            except ValueError:
                pass
        if properties.get("shape") in _RAIL_CLOCKWISE:
            properties["shape"] = _RAIL_CLOCKWISE[properties["shape"]]
    return make_block_state(block.name, properties)


BLOCK_COLORS = {
    "air": "#18202b", "stone": "#858b91", "cobblestone": "#70777d", "grass_block": "#63a447",
    "dirt": "#79553a", "oak_planks": "#bd955b", "spruce_planks": "#765334",
    "birch_planks": "#d6c583", "sand": "#d9cd86", "red_sand": "#b6673d",
    "water": "#3f76e4", "lava": "#e45b18", "glass": "#a9d5d6", "white_wool": "#e9ecec",
    "red_wool": "#a12722", "blue_wool": "#35399d", "green_wool": "#546d1b",
    "gold_block": "#f9d849", "iron_block": "#d8d8d8", "diamond_block": "#5cd7c8",
    "emerald_block": "#2acb58", "redstone_block": "#b51914", "obsidian": "#241b35",
    "netherrack": "#6e3c3c", "end_stone": "#d9dfa2", "barrier": "#d64747",
}


def block_color(block: BlockState) -> str:
    """Возвращает стабильный цвет блока для двумерного превью."""

    short_name = block.name.split(":", 1)[-1]
    if short_name in BLOCK_COLORS:
        return BLOCK_COLORS[short_name]
    for suffix, color in (("leaves", "#477a3d"), ("log", "#725334"), ("wood", "#725334"),
                          ("ore", "#777c80"), ("terracotta", "#9b6853"), ("concrete", "#7d7d7d")):
        if suffix in short_name:
            return color
    digest = hashlib.md5(short_name.encode("utf-8")).digest()
    return "#{:02x}{:02x}{:02x}".format(55 + digest[0] % 145, 55 + digest[1] % 145, 55 + digest[2] % 145)


def unique_states(blocks: Iterable[BlockState]) -> Tuple[BlockState, ...]:
    """Возвращает уникальные состояния, сохраняя порядок появления."""

    return tuple(dict.fromkeys(blocks))


def _build_standard_block_names() -> Tuple[str, ...]:
    """Формирует автономный список блоков Java Edition для автодополнения.

    Список ориентирован на реестр Minecraft 1.20.1 (DataVersion 3465), который
    используется конвертером по умолчанию. Семейства дерева, цветов, камня и
    меди генерируются программно, чтобы список было проще проверять и обновлять.
    """

    blocks = {
        # Природные блоки и жидкости.
        "air", "cave_air", "void_air", "stone", "deepslate", "cobbled_deepslate",
        "grass_block", "dirt", "coarse_dirt", "podzol", "rooted_dirt", "mud",
        "clay", "gravel", "sand", "red_sand", "sandstone", "red_sandstone",
        "ice", "packed_ice", "blue_ice", "snow", "snow_block", "powder_snow",
        "water", "lava", "bedrock", "obsidian", "crying_obsidian", "magma_block",
        "netherrack", "soul_sand", "soul_soil", "basalt", "smooth_basalt",
        "blackstone", "gilded_blackstone", "end_stone", "calcite", "tuff",
        "dripstone_block", "pointed_dripstone", "moss_block", "moss_carpet",
        "sculk", "sculk_vein", "sculk_catalyst", "sculk_shrieker", "sculk_sensor",
        "reinforced_deepslate", "farmland", "dirt_path", "mycelium",
        # Руды, сырьё и минеральные блоки.
        "coal_ore", "deepslate_coal_ore", "iron_ore", "deepslate_iron_ore",
        "copper_ore", "deepslate_copper_ore", "gold_ore", "deepslate_gold_ore",
        "redstone_ore", "deepslate_redstone_ore", "emerald_ore", "deepslate_emerald_ore",
        "lapis_ore", "deepslate_lapis_ore", "diamond_ore", "deepslate_diamond_ore",
        "nether_gold_ore", "nether_quartz_ore", "ancient_debris", "raw_iron_block",
        "raw_copper_block", "raw_gold_block", "coal_block", "iron_block", "gold_block",
        "redstone_block", "emerald_block", "lapis_block", "diamond_block",
        "netherite_block", "quartz_block", "quartz_bricks", "quartz_pillar",
        "chiseled_quartz_block", "smooth_quartz", "amethyst_block", "budding_amethyst",
        "small_amethyst_bud", "medium_amethyst_bud", "large_amethyst_bud", "amethyst_cluster",
        # Растения, грибы и кораллы.
        "grass", "fern", "dead_bush", "seagrass", "tall_seagrass", "dandelion", "poppy",
        "blue_orchid", "allium", "azure_bluet", "red_tulip", "orange_tulip", "white_tulip",
        "pink_tulip", "oxeye_daisy", "cornflower", "lily_of_the_valley", "wither_rose",
        "sunflower", "lilac", "tall_grass", "large_fern", "rose_bush", "peony",
        "brown_mushroom", "red_mushroom", "brown_mushroom_block", "red_mushroom_block",
        "mushroom_stem", "lily_pad", "sugar_cane", "cactus", "bamboo", "bamboo_sapling",
        "vine", "glow_lichen", "spore_blossom", "azalea", "flowering_azalea",
        "azalea_leaves", "flowering_azalea_leaves", "big_dripleaf", "big_dripleaf_stem",
        "small_dripleaf", "hanging_roots", "cave_vines", "cave_vines_plant",
        "twisting_vines", "twisting_vines_plant", "weeping_vines", "weeping_vines_plant",
        "nether_sprouts", "crimson_roots", "warped_roots", "nether_wart", "chorus_plant",
        "chorus_flower", "torchflower", "torchflower_crop", "pitcher_plant", "pitcher_crop",
        "wheat", "carrots", "potatoes", "beetroots", "melon_stem", "attached_melon_stem",
        "pumpkin_stem", "attached_pumpkin_stem", "sweet_berry_bush", "cocoa",
        "kelp", "kelp_plant", "sea_pickle", "tube_coral", "brain_coral", "bubble_coral",
        "fire_coral", "horn_coral", "dead_tube_coral", "dead_brain_coral", "dead_bubble_coral",
        "dead_fire_coral", "dead_horn_coral", "tube_coral_block", "brain_coral_block",
        "bubble_coral_block", "fire_coral_block", "horn_coral_block", "dead_tube_coral_block",
        "dead_brain_coral_block", "dead_bubble_coral_block", "dead_fire_coral_block",
        "dead_horn_coral_block", "tube_coral_fan", "brain_coral_fan", "bubble_coral_fan",
        "fire_coral_fan", "horn_coral_fan", "tube_coral_wall_fan", "brain_coral_wall_fan",
        "bubble_coral_wall_fan", "fire_coral_wall_fan", "horn_coral_wall_fan",
        # Функциональные и технические блоки.
        "crafting_table", "furnace", "blast_furnace", "smoker", "stonecutter", "cartography_table",
        "fletching_table", "smithing_table", "grindstone", "loom", "barrel", "chest",
        "trapped_chest", "ender_chest", "shulker_box", "dispenser", "dropper", "hopper",
        "observer", "piston", "sticky_piston", "piston_head", "moving_piston", "lever",
        "tripwire", "tripwire_hook", "daylight_detector", "target", "lightning_rod",
        "redstone_wire", "redstone_torch", "redstone_wall_torch", "redstone_lamp",
        "repeater", "comparator", "note_block", "jukebox", "lectern", "bell",
        "beacon", "conduit", "lodestone", "respawn_anchor", "enchanting_table", "anvil",
        "chipped_anvil", "damaged_anvil", "brewing_stand", "cauldron", "water_cauldron",
        "lava_cauldron", "powder_snow_cauldron", "composter", "beehive", "bee_nest",
        "campfire", "soul_campfire", "scaffolding", "ladder", "chain", "iron_bars",
        "glass", "glass_pane", "glowstone", "sea_lantern", "lantern", "soul_lantern",
        "torch", "wall_torch", "soul_torch", "soul_wall_torch", "end_rod", "flower_pot",
        "decorated_pot", "candle",
        "bookshelf", "chiseled_bookshelf", "cobweb", "sponge", "wet_sponge", "slime_block",
        "honey_block", "honeycomb_block", "hay_block", "dried_kelp_block", "bone_block",
        "melon", "pumpkin", "carved_pumpkin", "jack_o_lantern", "cake", "candle_cake",
        "tnt", "fire", "soul_fire", "spawner", "dragon_egg", "turtle_egg", "frogspawn",
        "infested_stone", "infested_cobblestone", "infested_stone_bricks",
        "infested_mossy_stone_bricks", "infested_cracked_stone_bricks", "infested_chiseled_stone_bricks",
        "end_portal", "end_portal_frame", "end_gateway", "nether_portal", "structure_block",
        "structure_void", "jigsaw", "barrier", "light", "command_block",
        "repeating_command_block", "chain_command_block",
        # Декоративные и строительные блоки.
        "bricks", "mud_bricks", "packed_mud", "prismarine", "prismarine_bricks",
        "dark_prismarine", "purpur_block", "purpur_pillar", "end_stone_bricks",
        "nether_bricks", "red_nether_bricks", "chiseled_nether_bricks", "cracked_nether_bricks",
        "nether_wart_block", "warped_wart_block", "shroomlight", "ochre_froglight",
        "verdant_froglight", "pearlescent_froglight", "smooth_stone", "smooth_sandstone",
        "cut_sandstone", "chiseled_sandstone", "smooth_red_sandstone", "cut_red_sandstone",
        "chiseled_red_sandstone", "stone_bricks", "mossy_stone_bricks", "cracked_stone_bricks",
        "chiseled_stone_bricks", "deepslate_bricks", "cracked_deepslate_bricks",
        "deepslate_tiles", "cracked_deepslate_tiles", "chiseled_deepslate",
        "polished_deepslate", "polished_blackstone", "polished_blackstone_bricks",
        "cracked_polished_blackstone_bricks", "chiseled_polished_blackstone",
        "white_terracotta", "terracotta", "suspicious_sand", "suspicious_gravel",
        "rail", "powered_rail", "detector_rail", "activator_rail", "iron_door",
        "iron_trapdoor", "stone_pressure_plate", "light_weighted_pressure_plate",
        "heavy_weighted_pressure_plate", "stone_button", "polished_blackstone_button",
        "polished_blackstone_pressure_plate", "dragon_head", "dragon_wall_head",
        "player_head", "player_wall_head", "skeleton_skull", "skeleton_wall_skull",
        "wither_skeleton_skull", "wither_skeleton_wall_skull", "zombie_head", "zombie_wall_head",
        "creeper_head", "creeper_wall_head", "piglin_head", "piglin_wall_head",
        "mangrove_roots", "muddy_mangrove_roots", "mangrove_propagule", "pink_petals",
        "sniffer_egg", "calibrated_sculk_sensor",
    }

    # Полные семейства обычной древесины.
    overworld_woods = ("oak", "spruce", "birch", "jungle", "acacia", "dark_oak", "mangrove", "cherry")
    for wood in overworld_woods:
        blocks.update({
            f"{wood}_log", f"{wood}_wood", f"stripped_{wood}_log", f"stripped_{wood}_wood",
            f"{wood}_planks", f"{wood}_stairs", f"{wood}_slab", f"{wood}_fence",
            f"{wood}_fence_gate", f"{wood}_door", f"{wood}_trapdoor", f"{wood}_pressure_plate",
            f"{wood}_button", f"{wood}_sign", f"{wood}_wall_sign", f"{wood}_hanging_sign",
            f"{wood}_wall_hanging_sign", f"{wood}_leaves", f"{wood}_sapling",
        })

    # Незерская древесина и бамбук отличаются составом семейства.
    for wood in ("crimson", "warped"):
        blocks.update({
            f"{wood}_stem", f"{wood}_hyphae", f"stripped_{wood}_stem", f"stripped_{wood}_hyphae",
            f"{wood}_planks", f"{wood}_stairs", f"{wood}_slab", f"{wood}_fence",
            f"{wood}_fence_gate", f"{wood}_door", f"{wood}_trapdoor", f"{wood}_pressure_plate",
            f"{wood}_button", f"{wood}_sign", f"{wood}_wall_sign", f"{wood}_hanging_sign",
            f"{wood}_wall_hanging_sign", f"{wood}_nylium", f"{wood}_fungus",
        })
    blocks.update({
        "bamboo_block", "stripped_bamboo_block", "bamboo_planks", "bamboo_mosaic",
        "bamboo_stairs", "bamboo_mosaic_stairs", "bamboo_slab", "bamboo_mosaic_slab",
        "bamboo_fence", "bamboo_fence_gate", "bamboo_door", "bamboo_trapdoor",
        "bamboo_pressure_plate", "bamboo_button", "bamboo_sign", "bamboo_wall_sign",
        "bamboo_hanging_sign", "bamboo_wall_hanging_sign",
    })

    # Цветные семейства.
    for color in COLORS:
        blocks.update({
            f"{color}_wool", f"{color}_carpet", f"{color}_concrete", f"{color}_concrete_powder",
            f"{color}_terracotta", f"{color}_glazed_terracotta", f"{color}_stained_glass",
            f"{color}_stained_glass_pane", f"{color}_shulker_box", f"{color}_bed",
            f"{color}_candle", f"{color}_candle_cake", f"{color}_banner", f"{color}_wall_banner",
        })

    # Каменные семейства с плитами, ступенями и стенами.
    stone_families = (
        "stone", "cobblestone", "mossy_cobblestone", "stone_brick", "mossy_stone_brick",
        "granite", "polished_granite", "diorite", "polished_diorite", "andesite",
        "polished_andesite", "cobbled_deepslate", "polished_deepslate", "deepslate_brick",
        "deepslate_tile", "blackstone", "polished_blackstone", "polished_blackstone_brick",
        "brick", "mud_brick", "sandstone", "smooth_sandstone", "cut_sandstone",
        "red_sandstone", "smooth_red_sandstone", "cut_red_sandstone", "nether_brick",
        "red_nether_brick", "end_stone_brick", "prismarine", "prismarine_brick",
        "dark_prismarine", "quartz", "smooth_quartz", "purpur",
    )
    wall_materials = {
        "cobblestone", "mossy_cobblestone", "stone_brick", "mossy_stone_brick",
        "granite", "diorite", "andesite", "cobbled_deepslate", "polished_deepslate",
        "deepslate_brick", "deepslate_tile", "blackstone", "polished_blackstone",
        "polished_blackstone_brick", "brick", "mud_brick", "sandstone", "red_sandstone",
        "nether_brick", "red_nether_brick", "end_stone_brick", "prismarine",
    }
    for material in stone_families:
        blocks.add(f"{material}_slab")
        if material not in ("cut_sandstone", "cut_red_sandstone"):
            blocks.add(f"{material}_stairs")
        if material in wall_materials:
            blocks.add(f"{material}_wall")

    potted_plants = {
        "oak_sapling", "spruce_sapling", "birch_sapling", "jungle_sapling", "acacia_sapling",
        "dark_oak_sapling", "mangrove_propagule", "cherry_sapling", "fern", "dandelion",
        "poppy", "blue_orchid", "allium", "azure_bluet", "red_tulip", "orange_tulip",
        "white_tulip", "pink_tulip", "oxeye_daisy", "cornflower", "lily_of_the_valley",
        "wither_rose", "red_mushroom", "brown_mushroom", "dead_bush", "cactus", "bamboo",
        "crimson_fungus", "warped_fungus", "crimson_roots", "warped_roots", "azalea_bush",
        "flowering_azalea_bush",
    }
    blocks.update(f"potted_{plant}" for plant in potted_plants)

    # Медные блоки всех стадий окисления и вощёные варианты.
    for prefix in ("", "exposed_", "weathered_", "oxidized_"):
        for form in ("copper", "cut_copper", "cut_copper_stairs", "cut_copper_slab"):
            blocks.add(f"{prefix}{form}")
            blocks.add(f"waxed_{prefix}{form}")

    return tuple(f"minecraft:{name}" for name in sorted(blocks))


# Готовый неизменяемый список используется двумя Combobox без повторной сборки.
STANDARD_BLOCK_NAMES = _build_standard_block_names()


def autocomplete_block_names(query: str, extra_names: Iterable[str] = (), limit: int = 200) -> Tuple[str, ...]:
    """Возвращает подходящие имена блоков для выпадающей подсказки."""

    needle = (query or "").strip().lower()
    candidates = set(STANDARD_BLOCK_NAMES)
    candidates.update(name for name in extra_names if name)
    if not needle:
        return tuple(sorted(candidates)[:limit])

    # Сначала показываются совпадения с началом строки, затем совпадения внутри.
    starts = sorted(name for name in candidates if name.startswith(needle))
    contains = sorted(name for name in candidates if needle in name and not name.startswith(needle))
    return tuple((starts + contains)[:limit])
