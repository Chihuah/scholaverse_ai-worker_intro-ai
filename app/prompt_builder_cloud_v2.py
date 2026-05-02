from __future__ import annotations

"""Cloud-ready prompt builder for fantasy RPG card generation.

This module is a cloud-image-generation variant of prompt_builder.py. It keeps
the same public entry points, but build_structured_description() now renders a
complete prompt that can be sent directly to gpt-image-2 without an additional
LLM rewriting layer.
"""

import hashlib
import json
import random
from typing import Any


RACE_MAP: dict[str, str] = {
    "elf": "elf",
    "human": "human",
    "orc": "orc",
    "dwarf": "dwarf",
    "goblin": "goblin",
    "dragon": "dragonborn",
    "pixie": "pixie",
    "plant": "plant humanoid",
    "slime": "slime humanoid",
}

GENDER_MAP: dict[str, str] = {
    "male": "male",
    "female": "female",
    "neutral": "androgynous",
}

RACE_VISUAL_RULES: dict[str, dict[str, list[str]]] = {
    "elf": {
        "mandatory": [
            "tall slender fantasy build with graceful posture",
            "long clearly pointed ears extending beyond the hair silhouette",
            "refined angular facial features with elegant cheekbones",
            "smooth high-fantasy presence rather than ordinary modern human styling",
            "light agile body language and poised noble bearing",
        ],
        "forbidden": [
            "ordinary rounded human ears",
            "plain fully human facial proportions",
            "stocky dwarf-like proportions",
        ],
    },
    "human": {
        "mandatory": [
            "fully human anatomy",
            "ordinary rounded human ears",
            "natural human skin texture and facial structure",
            "grounded adventurer appearance without non-human anatomy",
        ],
        "forbidden": [
            "non-human ears",
            "scales",
            "slime body texture",
            "plant bark skin",
            "tusks",
            "wings",
        ],
    },
    "orc": {
        "mandatory": [
            "broad heavy muscular fantasy build",
            "green or gray skin with rugged surface texture",
            "pronounced lower tusks visible from the mouth",
            "strong brow ridge and rugged non-human facial structure",
            "powerful shoulder line and imposing silhouette",
        ],
        "forbidden": [
            "delicate youthful human face",
            "handsome human portrait with only a slight green tint",
            "smooth ordinary human skin without tusks",
        ],
    },
    "dwarf": {
        "mandatory": [
            "short compact body proportions",
            "sturdy thick torso and low center of gravity",
            "shorter limbs with broad hands",
            "dense powerful dwarf physique",
            "solid grounded stance that reads as unmistakably dwarf",
        ],
        "forbidden": [
            "average-height human proportions",
            "long-legged silhouette",
            "slim human teenage body",
        ],
    },
    "goblin": {
        "mandatory": [
            "small wiry fantasy body",
            "oversized pointed ears that dominate the side silhouette",
            "sharp nose and mischievous angular non-human facial features",
            "greenish goblin skin",
            "quick restless posture with slightly hunched shoulders",
        ],
        "forbidden": [
            "human teenager appearance",
            "smooth elegant heroic human proportions",
            "cute ordinary childlike human face",
        ],
    },
    "dragon": {
        "mandatory": [
            "dragonborn humanoid anatomy",
            "visible scales across the face, neck, arms, and hands",
            "reptilian facial structure with a strong snout or muzzle shape",
            "horns, crest, or draconic head features",
            "clawed hands and clearly non-human draconic skin texture",
        ],
        "forbidden": [
            "smooth ordinary human skin",
            "human face with only tiny decorative horns",
            "plain human portrait without scales",
        ],
    },
    "pixie": {
        "mandatory": [
            "small fairy-like fantasy body with light delicate proportions",
            "translucent insect-like wings clearly visible behind the shoulders",
            "delicate non-human facial structure with bright alert eyes",
            "tiny magical glow particles around the body",
            "weightless hovering or tiptoe-light posture",
        ],
        "forbidden": [
            "ordinary human adult proportions",
            "wingless human portrait",
            "heavy armored bulky body",
        ],
    },
    "plant": {
        "mandatory": [
            "tree-like plant-humanoid anatomy inspired by walking tree beings",
            "woody bark body structure with branch-like limbs and trunk-like torso forms",
            "visible vines, moss, leaves, shoots, or small branch growth integrated into the body",
            "clearly non-human wooden facial structure rather than normal human skin",
            "an ancient living-tree presence similar to ent-like or groot-like fantasy plant beings",
        ],
        "forbidden": [
            "ordinary human skin",
            "plain human portrait with only a green palette",
            "human teenager appearance",
            "smooth human face with only leaf decorations",
        ],
    },
    "slime": {
        "mandatory": [
            "slime-humanoid anatomy",
            "wet sticky glossy gelatin body material",
            "clear translucency or semi-transparency in the body",
            "semi-transparent limbs, edges, or surface layers",
            "slippery reflective highlights across the slime surface",
            "soft fluid non-human silhouette cues instead of firm human skin anatomy",
        ],
        "forbidden": [
            "normal opaque human skin",
            "plain human portrait labeled as slime",
            "human teenager appearance",
            "dry matte skin texture",
        ],
    },
}

GENDER_VISUAL_RULES: dict[str, dict[str, list[str]]] = {
    "male": {
        "mandatory": [
            "masculine-coded facial structure with a firmer jaw line",
            "broader shoulder line and grounded body presentation",
            "mature heroic fantasy styling without glamour emphasis",
        ],
        "forbidden": [
            "strongly feminine glamour styling",
            "overtly delicate fashion-model presentation",
            "bare-chested or shirtless presentation",
        ],
    },
    "female": {
        "mandatory": [
            "feminine-coded facial structure with softer cheek and jaw contours",
            "balanced feminine body presentation suitable for fantasy character art",
            "elegant readable silhouette without excessive sexualization",
        ],
        "forbidden": [
            "masculine beard",
            "mustache",
            "heavy facial hair",
            "exaggerated pin-up pose",
            "revealing or skin-exposing armor",
            "bare midriff or exposed cleavage",
        ],
    },
    "neutral": {
        "mandatory": [
            "androgynous facial structure",
            "gender-ambiguous presentation with balanced masculine and feminine cues",
            "clean neutral hairstyle and clothing silhouette",
            "calm non-binary fantasy character reading",
        ],
        "forbidden": [
            "strongly masculine jawline and beard",
            "strongly feminine glamour styling",
            "clearly binary gender coding",
        ],
    },
}

CLASS_MAP: dict[str, str] = {
    "archmage": "archmage",
    "paladin": "paladin",
    "ranger": "ranger",
    "assassin": "assassin",
    "priest": "priest",
    "mage": "mage",
    "warrior": "warrior",
    "archer": "archer",
    "militia": "militia fighter",
    "apprentice": "apprentice",
    "farmer": "farmer",
}

CLASS_TO_COMBAT_STYLE: dict[str, str] = {
    "archmage": "caster",
    "priest": "caster",
    "mage": "caster",
    "apprentice": "caster",
    "paladin": "guardian_melee",
    "warrior": "guardian_melee",
    "militia": "guardian_melee",
    "ranger": "agile_ranged",
    "archer": "agile_ranged",
    "assassin": "rogue_agile",
    "farmer": "civilian_novice",
}

EQUIPMENT_MAP: dict[str, str] = {
    "legendary": "ornately engraved high-fantasy armor with gilded inlays, gemstone accents, and intricate filigree details",
    "fine": "well-crafted adventurer gear with polished metal fittings, fitted leather straps, and clean cloth layers",
    "common": "standard functional adventurer gear with simple cloth, leather belts, and practical protective pieces",
    "crude": "patched leather and rough-stitched cloth with mismatched metal scraps and visible wear",
    "broken": "tattered damaged gear with torn fabric, cracked leather, missing plates, and rough field repairs",
}

WEAPON_QUALITY_MAP: dict[str, str] = {
    "artifact": "legendary ornate artifact-grade",
    "fine": "finely crafted polished",
    "common": "standard functional",
    "crude": "crude worn",
    "primitive": "primitive makeshift",
}

WEAPON_TYPE_MAP: dict[str, str] = {
    "sword": "double-edged longsword with a simple cross-guard hilt",
    "shield": "kite shield with worn metal rim",
    "staff": "wooden staff with a small carved focus at the tip",
    "spellbook": "bound spellbook held close to the torso",
    "bow": "longbow with a simple leather-wrapped grip",
    "dagger": "short dagger with a narrow bright blade",
    "mace": "war mace with a heavy metal head",
    "spear": "battle spear with a leaf-shaped metal tip",
    "short_sword": "short sword with a compact straight blade",
    "club": "wooden club with rough natural grain",
    "wooden_stick": "simple wooden stick used as a beginner's staff",
    "stone": "crude stone weapon bound with leather strips",
}

BACKGROUND_MAP: dict[str, str] = {
    "palace_throne": "grand palace throne room with tall columns, polished marble floor, distant banners, and soft golden light",
    "dragon_lair": "vast dragon lair carved into volcanic rock, scattered gold coins, crystal clusters, faint smoke, and warm amber shafts of light",
    "sky_city": "floating fantasy city above a sea of clouds at sunrise, crystal spires, suspended bridges, waterfalls, and pink-gold sky",
    "castle": "medieval stone castle courtyard with banners, arched walls, distant towers, and clear heroic daylight",
    "magic_tower": "wizard tower chamber with shelves of books, arcane instruments, glowing runes, and candlelit blue-violet ambience",
    "town": "bustling medieval town square with timber buildings, hanging signs, market stalls, and warm afternoon light",
    "market": "lively market street with colorful cloth awnings, crates, baskets, distant shoppers, and warm sunlit haze",
    "village": "quiet rural village with thatched roofs, dirt path, wooden fences, soft greenery, and gentle morning light",
    "wilderness": "open wilderness with rolling grassland, distant mountains, wind-swept clouds, and broad natural light",
    "ruins": "ancient moss-covered ruins with broken stone arches, scattered columns, vines, and cool mysterious light",
}

EXPRESSION_MAP: dict[str, str] = {
    "regal": "regal commanding expression, head slightly raised, brow softly furrowed, gaze fixed forward with quiet authority",
    "passionate": "intense passionate expression, bright focused eyes, lifted brows, and mouth slightly open as if mid-battle cry",
    "confident": "confident expression, steady forward gaze, relaxed brow, and a faint controlled smile",
    "calm": "calm serene expression, softened eyes, relaxed mouth, and peaceful focused gaze",
    "weary": "weary expression, half-lowered eyelids, slight downward gaze, mouth gently closed, and faint shadows under the eyes",
}

POSE_MAP: dict[str, str] = {
    "charging": "charging forward with weight on the front leg, body leaning into motion, weapon arm extended, and free arm pulled back for balance",
    "battle_ready": "battle-ready stance with feet shoulder-width apart, knees slightly bent, weapon held at chest height in a guarded posture, gaze locked forward",
    "standing": "standing upright with balanced weight, relaxed shoulders, arms naturally arranged, and face directed toward the viewer",
    "crouching": "crouching low with bent knees, torso angled forward, one hand balancing the movement, and eyes alert",
}

LEVEL_ATMOSPHERE: list[tuple[int, int, str]] = [
    (1, 25, "muted earth tones, soft diffuse natural lighting, humble rustic atmosphere"),
    (26, 50, "vivid saturated colors, warm directional sunlight, optimistic adventurous atmosphere"),
    (51, 75, "dramatic chiaroscuro lighting, deep shadows, bright rim highlights, heroic high-fantasy atmosphere"),
    (76, 100, "epic cinematic lighting with volumetric god-rays, ethereal particles, legendary mythic atmosphere"),
]

RARITY_VISUAL: dict[str, str] = {
    "N": "clean simple linework, minimal ornamentation, restrained matte finish, effects kept subtle and minimal",
    "R": "moderate detail with crisp linework, subtle ambient glow around the character outline",
    "SR": "rich detailed rendering, cool blue or violet magical particle effects, ornate decorative motifs",
    "SSR": "highly detailed painterly rendering, radiant golden aura, intricate gold filigree, scattered light motes",
    "UR": "ultra-detailed rendering, divine prismatic glow, iridescent ethereal particles, mythic celestial atmosphere",
}

BORDER_STYLE_RULES: dict[str, dict[str, str]] = {
    "bronze": {
        "material_name": "weathered bronze frame",
        "prompt": "weathered bronze card border, aged bronze metal, subtle wear, humble fantasy craftsmanship",
        "accent": "muted bronze highlights with restrained ornament",
    },
    "steel": {
        "material_name": "tempered steel frame",
        "prompt": "polished tempered steel card border, cool reflective metal, crisp edges, disciplined forged craftsmanship",
        "accent": "clean steel highlights with restrained engraved lines",
    },
    "silver": {
        "material_name": "engraved silver frame",
        "prompt": "engraved silver card border, elegant silver filigree, refined magical ornament, bright silver sheen",
        "accent": "ornate silver filigree with refined fantasy engraving",
    },
    "gold": {
        "material_name": "royal gold frame",
        "prompt": "ornate royal gold card border, luminous gold metal, intricate regal engravings, prestigious high-fantasy craftsmanship",
        "accent": "radiant gold highlights with rich decorative detailing",
    },
    "prismatic": {
        "material_name": "prismatic aether frame",
        "prompt": "prismatic mythic card border, crystal-gold alloy, iridescent rainbow sheen, celestial energy, legendary ultimate rarity frame",
        "accent": "prismatic light refractions with mythic crystal ornament",
    },
    # Legacy aliases for older cards already saved in storage.
    "copper": {
        "material_name": "weathered bronze frame",
        "prompt": "weathered bronze card border, aged bronze metal, subtle wear, humble fantasy craftsmanship",
        "accent": "muted bronze highlights with restrained ornament",
    },
}

DEFAULT_STYLE_PROFILES: list[dict[str, Any]] = [
    {"name": "trading_card_painterly", "weight": 1},
    {"name": "anime_cel_shaded", "weight": 1},
    {"name": "classical_oil_painting", "weight": 1},
    {"name": "storybook_watercolor", "weight": 1},
    {"name": "arcane_crystal_illustration", "weight": 1},
    {"name": "jrpg_quest_card", "weight": 1},
    {"name": "illuminated_manuscript_fantasy", "weight": 1},
]

STYLE_BLOCK_BASE: dict[str, str] = {
    "trading_card_painterly": (
        "stylized high-fantasy digital trading card illustration, "
        "bold readable silhouette, semi-realistic heroic proportions, "
        "dramatic painterly lighting, polished collectible card presentation"
    ),
    "anime_cel_shaded": (
        "anime fantasy character card illustration, crisp clean linework, "
        "cel-shaded rendering, expressive eyes, vibrant saturated colors, "
        "polished modern character-card presentation"
    ),
    "classical_oil_painting": (
        "classical oil-painting fantasy portrait, visible textured brushstrokes, "
        "soft blended edges, rich chiaroscuro lighting, museum-quality fine-art finish"
    ),
    "storybook_watercolor": (
        "storybook fantasy watercolor illustration, soft translucent washes, "
        "gentle ink outlines, warm hand-painted texture, whimsical fairytale atmosphere"
    ),
    "arcane_crystal_illustration": (
        "luminous arcane fantasy illustration, glowing crystal highlights, "
        "transparent magical particles, radiant spell-light, elegant high-magic presentation"
    ),
    "jrpg_quest_card": (
        "JRPG-inspired fantasy character card illustration, "
        "bright adventurous color palette, clean stylized rendering, "
        "clear game-character silhouette, expressive readable face, "
        "optimistic quest-starting atmosphere, polished role-playing game card presentation"
    ),
    "illuminated_manuscript_fantasy": (
        "illuminated fantasy manuscript character card illustration, "
        "decorative parchment texture, delicate ink outlines, "
        "gold-leaf accents, medieval academy and quest-record aesthetic, "
        "elegant historical fantasy presentation"
    ),
}

# Legacy profile names from older saved cards and worker configuration are
# canonicalized to the new names above via STYLE_PROFILE_ALIASES. All lookups
# into STYLE_BLOCK_BASE must go through STYLE_PROFILE_ALIASES first.
STYLE_PROFILE_ALIASES: dict[str, str] = {
    "hearthstone_like_collectible_card": "trading_card_painterly",
    "anime_fantasy_character_card": "anime_cel_shaded",
    "painterly_fantasy_card": "classical_oil_painting",
}

CAMERA_ARCHETYPES: dict[str, dict[str, list[str]]] = {
    "hero_portrait": {
        "shot_type": [
            "head-and-shoulders close-up showing only face, neck, and shoulder line",
            "chest-up framing with arms partially visible",
            "waist-up framing showing the upper half of the body",
            "knee-up framing showing most of the body and pose",
        ],
        "camera_angle": ["eye-level view", "slightly low-angle view", "slight three-quarter angle", "frontal centered view"],
        "body_orientation": [
            "facing forward",
            "turned slightly left",
            "turned slightly right",
            "body angled with head facing viewer",
        ],
        "pose_family": [
            "standing calmly with relaxed shoulders, arms naturally arranged, and weight balanced between both feet",
            "confident presentation pose with chest open, one hand near the waist, and the head facing the viewer",
            "holding the object at rest near the torso, elbows relaxed, with the face unobstructed",
            "taking a first-step adventurer stance, one foot slightly forward and the body ready to move",
        ],
        "expression_family": [
            "calm focused expression with steady eyes and a neutral closed mouth",
            "determined expression with slightly furrowed brow and gaze fixed forward",
            "gentle confident expression with softened eyes and a faint restrained smile",
            "curious novice expression with alert eyes and composed mouth",
        ],
        "lighting": [
            "soft directional daylight across the face",
            "warm rim light outlining the shoulders",
            "clean studio-like fantasy card lighting",
        ],
        "mood": ["hopeful beginning", "quiet determination", "fresh adventurer energy"],
        "color_palette": ["warm natural tones", "balanced vivid fantasy colors", "soft gold and teal accents"],
        "composition_rules": [
            "single character",
            "character is the clear visual focus",
            "clear character outline with visible facial features and clothing details",
            "face clearly visible",
            "reserved visual space for readable English card text",
        ],
    },
    "guardian_stance": {
        "shot_type": [
            "chest-up framing with weapon held high near the head",
            "waist-up framing showing torso, arms, and weapon clearly",
            "knee-up framing with weapon visible and stance grounded",
            "full-body shot from head to toe with feet planted firmly on the ground",
        ],
        "camera_angle": ["eye-level view", "frontal centered view", "slightly low-angle view"],
        "body_orientation": [
            "facing forward",
            "body angled with head facing viewer",
            "torso turned slightly while feet stay planted",
        ],
        "pose_family": [
            "battle-ready stance with feet shoulder-width apart, knees slightly bent, and weapon held at chest height",
            "standing firmly with shield-side shoulder forward, weapon kept low but ready, and gaze locked ahead",
            "guarded heroic stance with the weapon angled diagonally beside the body and both hands readable",
            "protective stance with weight grounded through both legs and the upper body squared toward the viewer",
        ],
        "expression_family": [
            "serious heroic expression with focused eyes and tightened mouth",
            "determined expression with lowered brow and direct forward gaze",
            "calm focused expression with disciplined posture and controlled breathing",
        ],
        "lighting": ["dramatic front light with subtle rim highlights", "torch-warm fantasy lighting", "heroic sunset side light"],
        "mood": ["brave defense", "disciplined readiness", "steadfast guardian resolve"],
        "color_palette": ["bronze and steel tones", "warm amber and deep blue shadows", "heroic red-gold accents"],
        "composition_rules": [
            "single character",
            "character is the clear visual focus",
            "clear character outline with visible facial features and clothing details",
            "face clearly visible",
            "weapon clearly visible",
            "reserved visual space for readable English card text",
        ],
    },
    "spellcasting_scene": {
        "shot_type": [
            "chest-up framing centered on the face and casting hand",
            "waist-up framing showing the torso, both hands, and surrounding spell-light",
            "knee-up framing with magical effects swirling around the body",
            "full-body shot from head to toe with robes and spell aura fully visible",
        ],
        "camera_angle": ["slight three-quarter angle", "slightly low-angle view", "eye-level view"],
        "body_orientation": [
            "facing forward",
            "turned slightly left",
            "turned slightly right",
            "body angled with head facing viewer",
        ],
        "pose_family": [
            "casting magic with one hand raised near shoulder height, fingers open, and glowing energy gathered around the palm",
            "staff held diagonally in a controlled casting posture while the free hand shapes a small spell circle",
            "spellbook or focus held close to the torso while the eyes look forward over the magical light",
            "robes and small particles moving gently as if stirred by a controlled arcane breeze",
        ],
        "expression_family": [
            "mysterious expression with narrowed eyes and a faint knowing smile",
            "calm focused expression with eyes reflecting magical light",
            "determined expression with brow slightly furrowed and mouth firmly closed",
        ],
        "lighting": ["cool blue arcane glow from the hands", "violet magical side light", "soft candlelight mixed with spell-light"],
        "mood": ["arcane concentration", "quiet wonder", "controlled magical power"],
        "color_palette": ["cool blues and violet highlights", "teal spell glow with warm gold accents", "deep indigo and silver"],
        "composition_rules": [
            "single character",
            "character is the clear visual focus",
            "clear character outline with visible facial features and clothing details",
            "face clearly visible",
            "hands clearly readable",
            "reserved visual space for readable English card text",
        ],
    },
    "agile_action_pose": {
        "shot_type": [
            "chest-up framing capturing intense facial focus and weapon ready",
            "waist-up framing with the body twisted in motion",
            "knee-up framing showing footwork and balanced stance",
            "full-body shot from head to toe showing the entire dynamic pose",
        ],
        "camera_angle": ["slight three-quarter angle", "eye-level view", "slightly low-angle view"],
        "body_orientation": [
            "facing forward",
            "turned slightly left",
            "turned slightly right",
            "body angled with head facing viewer",
        ],
        "pose_family": [
            "forward-leaning agile stance with weight on the front leg, rear leg ready to spring, and weapon kept clear of the face",
            "swift poised stance with one shoulder leading, elbows bent, and the silhouette readable",
            "crouched action-ready posture with knees bent, torso angled, and eyes locked forward",
            "light evasive pose with the object held close to the body and the free hand balancing the movement",
        ],
        "expression_family": [
            "focused expression with sharp eyes and controlled mouth",
            "serious heroic expression with intense forward gaze",
            "confident expression with raised brow and slight smirk",
        ],
        "lighting": ["crisp directional adventure lighting", "cool rim light tracing the action silhouette", "dramatic diagonal light across the face"],
        "mood": ["quick movement", "alert readiness", "adventurous momentum"],
        "color_palette": ["high-contrast adventure colors", "forest greens and leather browns", "cool shadows with bright highlight accents"],
        "composition_rules": [
            "single character",
            "character is the clear visual focus",
            "clear character outline with visible facial features and clothing details",
            "face clearly visible",
            "pose readable",
            "facial features clearly visible",
            "reserved visual space for readable English card text",
        ],
    },
    "elegant_card_pose": {
        "shot_type": [
            "head-and-shoulders close-up centered on the face and refined expression",
            "chest-up framing showing collar, jewelry, and graceful upper-body posture",
            "waist-up framing showing the upper costume and one elegant hand gesture",
            "knee-up framing showing the costume silhouette and posed stance",
        ],
        "camera_angle": ["slight three-quarter angle", "eye-level view", "slightly low-angle view", "frontal centered view"],
        "body_orientation": [
            "facing forward",
            "body angled with head facing viewer",
            "turned slightly left",
            "turned slightly right",
        ],
        "pose_family": [
            "graceful display pose with the shoulders turned, chin slightly lifted, and hands placed elegantly within the frame",
            "formal character-card pose with one hand near the chest and the other relaxed at the side",
            "calm noble stance with vertical posture, balanced shoulders, and a clearly readable costume silhouette",
            "portrait-ready pose with the object held low or to the side so the face and text areas remain unobstructed",
        ],
        "expression_family": [
            "gentle confident expression with softened eyes and a refined faint smile",
            "mysterious expression with calm eyes and restrained mouth",
            "calm focused expression with dignified gaze and relaxed brow",
        ],
        "lighting": ["soft painterly key light", "elegant gold-rimmed portrait lighting", "diffused manuscript-like illumination"],
        "mood": ["refined achievement", "quiet prestige", "elegant fantasy record"],
        "color_palette": ["soft gold and ivory", "rich jewel tones", "muted parchment colors with luminous accents"],
        "composition_rules": [
            "single character",
            "character is the clear visual focus",
            "clear character outline with visible facial features and clothing details",
            "face clearly visible",
            "reserved visual space for readable English card text",
        ],
    },
}

BASE_ARCHETYPE_WEIGHTS: dict[str, dict[str, int]] = {
    "civilian_novice": {
        "hero_portrait": 50,
        "guardian_stance": 0,
        "spellcasting_scene": 0,
        "agile_action_pose": 0,
        "elegant_card_pose": 15,
    },
    "caster": {
        "hero_portrait": 30,
        "guardian_stance": 5,
        "spellcasting_scene": 45,
        "agile_action_pose": 5,
        "elegant_card_pose": 20,
    },
    "guardian_melee": {
        "hero_portrait": 25,
        "guardian_stance": 45,
        "spellcasting_scene": 0,
        "agile_action_pose": 10,
        "elegant_card_pose": 20,
    },
    "agile_ranged": {
        "hero_portrait": 25,
        "guardian_stance": 5,
        "spellcasting_scene": 0,
        "agile_action_pose": 45,
        "elegant_card_pose": 20,
    },
    "rogue_agile": {
        "hero_portrait": 20,
        "guardian_stance": 5,
        "spellcasting_scene": 0,
        "agile_action_pose": 50,
        "elegant_card_pose": 20,
    },
    "martial_unarmed": {
        "hero_portrait": 30,
        "guardian_stance": 20,
        "spellcasting_scene": 0,
        "agile_action_pose": 30,
        "elegant_card_pose": 20,
    },
}

UNLOCK_STAGE_MULTIPLIERS: dict[str, dict[str, float]] = {
    "no_class": {
        "hero_portrait": 1.0,
        "guardian_stance": 0.0,
        "spellcasting_scene": 0.0,
        "agile_action_pose": 0.0,
        "elegant_card_pose": 0.75,
    },
    "class_no_weapon": {
        "hero_portrait": 1.0,
        "guardian_stance": 0.8,
        "spellcasting_scene": 0.8,
        "agile_action_pose": 0.8,
        "elegant_card_pose": 1.0,
    },
    "full_weapon_unlocked": {
        "hero_portrait": 1.0,
        "guardian_stance": 1.0,
        "spellcasting_scene": 1.0,
        "agile_action_pose": 1.0,
        "elegant_card_pose": 1.0,
    },
}

RARITY_ELEGANT_MULTIPLIER: dict[str, float] = {
    "N": 1.0,
    "R": 1.1,
    "SR": 1.25,
    "SSR": 1.4,
    "UR": 1.6,
}

STARTER_OBJECT_RULES: dict[str, dict[str, Any]] = {
    "civilian_novice": {
        "object_state": "empty_handed",
        "object_prompt": "empty-handed",
    },
    "caster": {
        "object_state": "starter_object",
        "object_prompt": "holding a simple wooden staff",
    },
    "guardian_melee": {
        "object_state": "starter_object",
        "object_prompt": "holding a plain short sword",
    },
    "agile_ranged": {
        "object_state": "starter_object",
        "object_prompt": "holding a simple hunting bow",
    },
    "rogue_agile": {
        "object_state": "starter_object",
        "object_prompt": "holding a plain dagger",
    },
    "martial_unarmed": {
        "object_state": "empty_handed",
        "object_prompt": "empty-handed or wearing simple hand wraps",
    },
}


def _get_class_value(card_config: dict[str, Any]) -> str | None:
    return card_config.get("class") or card_config.get("class_") or None


def _lookup_level_atmosphere(level: int) -> str:
    for low, high, description in LEVEL_ATMOSPHERE:
        if low <= level <= high:
            return description
    return LEVEL_ATMOSPHERE[0][2]


def _normalize_key(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).strip().lower().replace(" ", "_")


def _metadata_value(attribute_metadata: dict[str, Any] | None, key: str, field: str = "english_hint") -> str | None:
    if not attribute_metadata:
        return None
    item = attribute_metadata.get(key)
    if not isinstance(item, dict):
        return None
    value = item.get(field)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _pick_weighted(options: dict[str, float], rng: random.Random | None) -> str:
    filtered = [(name, weight) for name, weight in options.items() if weight > 0]
    if not filtered:
        raise ValueError("No weighted options available")
    if rng is None:
        return max(filtered, key=lambda item: item[1])[0]
    names = [name for name, _ in filtered]
    weights = [weight for _, weight in filtered]
    return rng.choices(names, weights=weights, k=1)[0]


def _pick_list_value(values: list[str], rng: random.Random | None) -> str:
    if not values:
        raise ValueError("Expected non-empty candidate list")
    if rng is None:
        return values[0]
    return rng.choice(values)


def _fallback_value(mapping: dict[str, str], raw_value: str | None, default: str | None = None) -> str | None:
    key = _normalize_key(raw_value)
    if not key:
        return default
    return mapping.get(key, raw_value)


def _stable_rng_seed(
    card_config: dict[str, Any],
    learning_data: dict[str, Any],
    student_nickname: str,
    style_hint: str | None,
) -> int:
    payload = {
        "card_config": card_config,
        "learning_data": learning_data,
        "student_nickname": student_nickname,
        "style_hint": style_hint or "",
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def resolve_unlock_stage(card_config: dict[str, Any]) -> str:
    class_name = _get_class_value(card_config)
    weapon_quality = card_config.get("weapon_quality")
    weapon_type = card_config.get("weapon_type")
    if not class_name:
        return "no_class"
    if weapon_quality and weapon_type:
        return "full_weapon_unlocked"
    return "class_no_weapon"


def resolve_combat_style(
    class_name: str | None,
    attribute_metadata: dict[str, Any] | None = None,
) -> str:
    metadata_style = _metadata_value(attribute_metadata, "class", field="combat_style")
    if metadata_style:
        return metadata_style
    class_key = _normalize_key(class_name)
    if not class_key:
        return "civilian_novice"
    return CLASS_TO_COMBAT_STYLE.get(class_key, "civilian_novice")


def _build_conflict_rules(race_key: str | None, gender_key: str | None) -> list[str]:
    rules: list[str] = []

    if race_key == "dwarf":
        rules.append("keep unmistakably short compact dwarf proportions")
        if gender_key in {"female", "neutral"}:
            rules.append("do not add a beard, mustache, or heavy facial hair")

    if race_key == "goblin":
        rules.append("do not render the character as a human child or human teenager")

    if race_key in {"plant", "slime"}:
        rules.append("race material traits must be clearly visible in the skin and body, not only implied by color")
        rules.append("do not collapse the character into an ordinary human portrait")
    if race_key == "plant":
        rules.append("the body should read primarily as a living tree or woody plant being, not a human wearing plant accessories")
    if race_key == "slime":
        rules.append("the body should visibly read as wet translucent slime material rather than normal skin")

    if race_key == "dragon":
        rules.append("keep clearly visible draconic scales and reptilian facial structure")
        rules.append("do not reduce the design to a human with small horn accessories")

    if gender_key == "neutral":
        rules.append("keep the presentation visibly androgynous and avoid a strongly male-only or female-only reading")

    return rules


def resolve_character_facts(
    card_config: dict[str, Any],
    learning_data: dict[str, Any],
    student_nickname: str = "",
    attribute_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del learning_data  # reserved for future use

    race_key = _normalize_key(card_config.get("race"))
    gender_key = _normalize_key(card_config.get("gender"))
    class_name = _metadata_value(attribute_metadata, "class") or _fallback_value(CLASS_MAP, _get_class_value(card_config))
    combat_style = resolve_combat_style(class_name, attribute_metadata)
    race_rule = RACE_VISUAL_RULES.get(race_key or "", {"mandatory": [], "forbidden": []})
    gender_rule = GENDER_VISUAL_RULES.get(gender_key or "", {"mandatory": [], "forbidden": []})

    facts = {
        "race_key": race_key,
        "race": _metadata_value(attribute_metadata, "race") or _fallback_value(RACE_MAP, card_config.get("race")),
        "gender_key": gender_key,
        "gender": _metadata_value(attribute_metadata, "gender") or _fallback_value(GENDER_MAP, card_config.get("gender")),
        "class_name": class_name,
        "combat_style": combat_style,
        "equipment": _metadata_value(attribute_metadata, "equipment") or _fallback_value(EQUIPMENT_MAP, card_config.get("equipment")),
        "background": _metadata_value(attribute_metadata, "background") or _fallback_value(BACKGROUND_MAP, card_config.get("background")),
        "expression": _metadata_value(attribute_metadata, "expression") or _fallback_value(EXPRESSION_MAP, card_config.get("expression")),
        "pose": _metadata_value(attribute_metadata, "pose") or _fallback_value(POSE_MAP, card_config.get("pose")),
        "weapon_quality": _metadata_value(attribute_metadata, "weapon_quality") or _fallback_value(WEAPON_QUALITY_MAP, card_config.get("weapon_quality")),
        "weapon_type": _metadata_value(attribute_metadata, "weapon_type") or _fallback_value(WEAPON_TYPE_MAP, card_config.get("weapon_type")),
        "level": int(card_config.get("level", 1)),
        "rarity": str(card_config.get("rarity", "N")),
        "border": str(card_config.get("border", "copper")),
        "student_nickname": student_nickname,
        "race_mandatory_traits": list(race_rule["mandatory"]),
        "race_forbidden_traits": list(race_rule["forbidden"]),
        "gender_mandatory_traits": list(gender_rule["mandatory"]),
        "gender_forbidden_traits": list(gender_rule["forbidden"]),
        "conflict_rules": _build_conflict_rules(race_key, gender_key),
    }
    return facts


def choose_style_profile(
    rarity: str,
    style_profiles: list[dict[str, Any]] | None = None,
    rng: random.Random | None = None,
) -> str:
    """Choose a canonical style profile name.

    Legacy profile names are accepted through STYLE_PROFILE_ALIASES, but this
    cloud-v2 builder returns the new canonical names in direction_spec.
    """
    del rarity  # reserved for future rarity-aware weighting
    profiles = style_profiles or DEFAULT_STYLE_PROFILES
    weights: dict[str, float] = {}
    for item in profiles:
        raw_name = str(item["name"])
        name = STYLE_PROFILE_ALIASES.get(raw_name, raw_name)
        weights[name] = weights.get(name, 0.0) + float(item.get("weight", 1))
    return _pick_weighted(weights, rng)


def choose_camera_spec(
    combat_style: str,
    unlock_stage: str,
    rarity: str,
    explicit_pose: str | None = None,
    explicit_expression: str | None = None,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    base_weights = dict(BASE_ARCHETYPE_WEIGHTS.get(combat_style, BASE_ARCHETYPE_WEIGHTS["civilian_novice"]))
    stage_multipliers = UNLOCK_STAGE_MULTIPLIERS[unlock_stage]
    weighted: dict[str, float] = {}
    for archetype_name, base_weight in base_weights.items():
        value = float(base_weight) * stage_multipliers.get(archetype_name, 0.0)
        if archetype_name == "elegant_card_pose":
            value *= RARITY_ELEGANT_MULTIPLIER.get(rarity, 1.0)
        weighted[archetype_name] = value

    archetype = _pick_weighted(weighted, rng)
    config = CAMERA_ARCHETYPES[archetype]
    pose_family = explicit_pose or _pick_list_value(config["pose_family"], rng)
    expression_family = explicit_expression or _pick_list_value(config["expression_family"], rng)

    return {
        "archetype": archetype,
        "shot_type": _pick_list_value(config["shot_type"], rng),
        "camera_angle": _pick_list_value(config["camera_angle"], rng),
        "body_orientation": _pick_list_value(config["body_orientation"], rng),
        "pose_family": pose_family,
        "expression_family": expression_family,
        "lighting": _pick_list_value(config["lighting"], rng),
        "mood": _pick_list_value(config["mood"], rng),
        "color_palette": _pick_list_value(config["color_palette"], rng),
        "composition_rules": list(config["composition_rules"]),
    }


def build_object_rule(
    unlock_stage: str,
    combat_style: str,
    card_config: dict[str, Any],
    attribute_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if unlock_stage == "no_class":
        return {
            "object_state": "empty_handed",
            "object_prompt": "both hands empty, unarmed, no weapon, no tool, no object",
            "visibility_rule": "hands visible, clearly empty, and unarmed",
            "forbidden_objects": [
                "sword",
                "staff",
                "bow",
                "dagger",
                "shield",
                "spellbook",
                "tool",
                "blade",
                "hilt",
                "combat accessory",
            ],
        }

    if unlock_stage == "class_no_weapon":
        starter = STARTER_OBJECT_RULES.get(combat_style, STARTER_OBJECT_RULES["civilian_novice"])
        return {
            "object_state": starter["object_state"],
            "object_prompt": starter["object_prompt"],
            "visibility_rule": "object clearly visible, held naturally near the body, and not blocking the face, nameplate, level badge, or rarity mark",
            "forbidden_objects": [
                "ornate legendary weapon",
                "multiple weapons",
                "large floating props",
                "oversized object covering the character",
            ],
        }

    weapon_quality = _metadata_value(attribute_metadata, "weapon_quality") or _fallback_value(
        WEAPON_QUALITY_MAP, card_config.get("weapon_quality"), default="standard"
    )
    weapon_type = _metadata_value(attribute_metadata, "weapon_type") or _fallback_value(
        WEAPON_TYPE_MAP, card_config.get("weapon_type"), default="weapon"
    )
    return {
        "object_state": "actual_weapon",
        "object_prompt": f"holding a {weapon_quality} {weapon_type} in a readable fantasy-card pose",
        "visibility_rule": "weapon clearly visible but not blocking the face, nameplate, level badge, or rarity mark; weapon should occupy less than one third of the image area",
        "forbidden_objects": [
            "multiple weapons",
            "extra companions",
            "oversized floating relics",
            "weapon covering the face",
            "weapon covering the card text",
        ],
    }


def build_text_rule(student_nickname: str, level: int, rarity: str) -> dict[str, Any]:
    nickname = str(student_nickname or "Student").strip() or "Student"
    return {
        "text_mode": "render_in_image",
        "nameplate": {
            "text": nickname,
            "position": "bottom_center",
            "container": "parchment_scroll",
            "typography": "serif fantasy font, dark brown ink, single line",
        },
        "level_badge": {
            "text": str(level),
            "position": "top_left",
            "container": "round_badge",
            "show_prefix": False,
            "typography": "bold serif digits, dark ink, centered inside the badge",
        },
        "rarity_mark": {
            "text": str(rarity),
            "position": "top_right",
            "container": "plain_letter_mark",
            "typography": "bold serif capital letters, dark ink or engraved metallic mark",
        },
        "layout_constraints": [
            "all rendered text must be readable and spelled exactly as requested",
            "text must not overlap the face, weapon, hands, or decorative border",
            "the bottom parchment nameplate must be compact, centered, and occupy only the lower band of the card",
            "do not duplicate the nickname, level number, or rarity mark anywhere else",
            "do not render any extra captions, titles, subtitles, labels, logos, signatures, or watermarks",
        ],
    }


def build_border_rule(border: str, rarity: str) -> dict[str, Any]:
    del rarity  # reserved for future border/rarity cross-tuning
    normalized = str(border or "bronze").strip().lower()
    rule = BORDER_STYLE_RULES.get(normalized, BORDER_STYLE_RULES["bronze"])
    return {
        "border_style": normalized,
        "material_name": rule["material_name"],
        "frame_prompt": rule["prompt"],
        "accent_rule": rule["accent"],
        "layout_rule": "the decorative border must stay on the outer frame, leave clear inner margin for the character, and must not intrude into the face, weapon, level badge, rarity mark, or nameplate",
    }


def assemble_direction_spec(
    unlock_stage: str,
    style_profile: str,
    camera_spec: dict[str, Any],
    object_rule: dict[str, Any],
    text_rule: dict[str, Any],
    border_rule: dict[str, Any],
    style_hint: str | None = None,
) -> dict[str, Any]:
    direction = {
        "unlock_stage": unlock_stage,
        "style_profile": style_profile,
        **camera_spec,
        "object_rule": object_rule,
        "text_rule": text_rule,
        "border_rule": border_rule,
    }
    if style_hint:
        direction["style_hint"] = style_hint.strip()
    return direction


def build_prompt_spec(
    card_config: dict[str, Any],
    learning_data: dict[str, Any],
    student_nickname: str = "",
    attribute_metadata: dict[str, Any] | None = None,
    rng_seed: int | None = None,
    style_hint: str | None = None,
) -> dict[str, Any]:
    seed_value = (
        rng_seed
        if rng_seed is not None
        else _stable_rng_seed(card_config, learning_data, student_nickname, style_hint)
    )
    rng = random.Random(seed_value)
    character_facts = resolve_character_facts(
        card_config=card_config,
        learning_data=learning_data,
        student_nickname=student_nickname,
        attribute_metadata=attribute_metadata,
    )
    unlock_stage = resolve_unlock_stage(card_config)
    combat_style = resolve_combat_style(character_facts.get("class_name"), attribute_metadata)
    character_facts["combat_style"] = combat_style

    style_profile = choose_style_profile(
        rarity=character_facts["rarity"],
        rng=rng,
    )
    camera_spec = choose_camera_spec(
        combat_style=combat_style,
        unlock_stage=unlock_stage,
        rarity=character_facts["rarity"],
        explicit_pose=character_facts.get("pose"),
        explicit_expression=character_facts.get("expression"),
        rng=rng,
    )
    object_rule = build_object_rule(
        unlock_stage=unlock_stage,
        combat_style=combat_style,
        card_config=card_config,
        attribute_metadata=attribute_metadata,
    )
    text_rule = build_text_rule(
        student_nickname=student_nickname,
        level=character_facts["level"],
        rarity=character_facts["rarity"],
    )
    border_rule = build_border_rule(
        border=character_facts["border"],
        rarity=character_facts["rarity"],
    )
    direction_spec = assemble_direction_spec(
        unlock_stage=unlock_stage,
        style_profile=style_profile,
        camera_spec=camera_spec,
        object_rule=object_rule,
        text_rule=text_rule,
        border_rule=border_rule,
        style_hint=style_hint,
    )

    return {
        "schema_version": "cloud_v2",
        "character_facts": character_facts,
        "direction_spec": direction_spec,
    }


def _quote_literal_text(value: Any) -> str:
    """Return a safely quoted literal text instruction for image text rendering."""
    text = str(value if value is not None else "").strip()
    text = text.replace('"', "'")
    return f'"{text}"'


def _join_rules(rules: list[str] | tuple[str, ...]) -> str:
    return "; ".join(rule.strip().rstrip(".") for rule in rules if str(rule).strip())


def render_prompt_spec_for_cloud_image(spec: dict[str, Any]) -> str:
    """Render a direct cloud-ready prompt for gpt-image-2.

    The order follows the cloud prompt design goal: scene -> subject -> details
    -> card frame and text -> constraints. Literal card text is always wrapped
    in double quotes so the image model treats it as exact text.
    """
    facts = spec["character_facts"]
    direction = spec["direction_spec"]
    object_rule = direction["object_rule"]
    text_rule = direction["text_rule"]
    border_rule = direction["border_rule"]

    style_profile = STYLE_PROFILE_ALIASES.get(direction["style_profile"], direction["style_profile"])
    style_base = STYLE_BLOCK_BASE.get(style_profile, STYLE_BLOCK_BASE["trading_card_painterly"])
    atmosphere = _lookup_level_atmosphere(int(facts.get("level") or 1))
    rarity_visual = RARITY_VISUAL.get(str(facts.get("rarity") or "N"), RARITY_VISUAL["N"])

    race = facts.get("race") or "unspecified fantasy race"
    gender = facts.get("gender") or "unspecified gender presentation"
    class_name = facts.get("class_name") or "novice adventurer without a formal class"
    equipment = facts.get("equipment") or "simple basic clothing"
    background = facts.get("background") or "modest fantasy background"
    nickname_text = _quote_literal_text(text_rule["nameplate"]["text"])
    level_text = _quote_literal_text(text_rule["level_badge"]["text"])
    rarity_text = _quote_literal_text(text_rule["rarity_mark"]["text"])

    mandatory_traits = _join_rules(facts.get("race_mandatory_traits", []))
    gender_traits = _join_rules(facts.get("gender_mandatory_traits", []))
    conflict_rules = _join_rules(facts.get("conflict_rules", []))
    forbidden_traits = _join_rules(
        list(facts.get("race_forbidden_traits", []))
        + list(facts.get("gender_forbidden_traits", []))
        + list(object_rule.get("forbidden_objects", []))
    )

    no_class_rule = ""
    if direction["unlock_stage"] == "no_class":
        no_class_rule = " Do not describe the character as any class, profession, or combat role."

    composition_rules_text = _join_rules(direction.get("composition_rules", []))

    lines = [
        "Create a vertical high-fantasy collectible RPG character card illustration.",
        "",
        "Scene:",
        (
            f"Use this visual style: {style_base}. Place the character in {background}, "
            f"with {direction['lighting']}, {direction['mood']}, {direction['color_palette']}, "
            f"{atmosphere}, and {rarity_visual}. Keep the background secondary to the character, "
            "softly defocused, and not cluttered."
        ),
        "",
        "Subject:",
        (
            f"A single {gender} {race} {class_name}. Race traits must be visible: {mandatory_traits or 'clear fantasy race traits'}. "
            f"Gender presentation: {gender_traits or 'clear but tasteful character presentation'}. {no_class_rule}".strip()
        ),
        "",
        "Details:",
        (
            f"The character wears {equipment}. The character is shown as a {direction['shot_type']}, "
            f"{direction['camera_angle']}, {direction['body_orientation']}. Pose: {direction['pose_family']}. "
            f"Expression: {direction['expression_family']}. Object rule: {object_rule['object_prompt']}; "
            f"{object_rule['visibility_rule']}."
        ),
        "",
        "Composition requirements:",
        f"{composition_rules_text or 'single character; clear visual focus; face clearly visible; readable silhouette'}.",
        "",
        "Card frame and text:",
        (
            f"Use {border_rule['frame_prompt']}; {border_rule['accent_rule']}. "
            f"{border_rule['layout_rule']}."
        ),
        (
            f"Top-left round metal badge contains exactly the text {level_text}, "
            f"{text_rule['level_badge'].get('typography', 'bold readable digits')}."
        ),
        (
            f"Top-right rarity mark contains exactly the text {rarity_text}, "
            f"{text_rule['rarity_mark'].get('typography', 'bold readable letters')}."
        ),
        (
            f"Bottom-center compact parchment scroll nameplate contains exactly the text {nickname_text}, "
            f"{text_rule['nameplate'].get('typography', 'readable fantasy font')}; the scroll occupies only a small lower band of the card."
        ),
        "",
        "Constraints:",
        "- Single character only; face clearly visible; pose readable; clear character silhouette.",
        "- No extra characters, companions, animals, duplicated bodies, extra weapons, cluttered props, or obscured face.",
        f"- Avoid: {forbidden_traits or 'unintended race, gender, or object drift'}.",
        f"- Conflict rules: {conflict_rules or 'prioritize exact race, text, and card layout requirements'}.",
        f"- Text rules: {_join_rules(text_rule['layout_constraints'])}.",
        "- Do not render any other letters, captions, labels, title text, subtitles, logos, signatures, watermarks, or UI text.",
        "- All characters must be fully clothed in tasteful fantasy attire suitable for an educational platform; no nudity, no exposed cleavage, no bare midriff, no revealing or skin-exposing armor.",
    ]
    # Cloud render intentionally ignores direction["style_hint"]: the legacy
    # SD-era style_hint default ("Hearthstone-style fantasy card art ...") is
    # too dominant when placed at the top of a structured prompt and overrides
    # the chosen style_profile. The 7 style profiles + per-archetype
    # lighting/mood/color_palette already provide enough variety. To re-enable
    # an admin-customized hint in the future, append it inside the Constraints
    # block instead of inserting at the top.
    return "\n".join(lines)


def render_prompt_spec_for_cloud_edit(spec: dict[str, Any]) -> str:
    """Render a prompt for gpt-image-2 ``client.images.edit``.

    Companion to :func:`render_prompt_spec_for_cloud_image` for image-edit
    flows where a reference card image carries the character's locked
    identity. The reference image is supplied to the OpenAI API separately;
    this function only produces the text portion of the request.

    Identity preserved from the reference image (face, race, body, gender,
    hair) is stated explicitly in a "preserve" block; everything that should
    differ for the new card (class, equipment, weapon, pose, framing,
    background, atmosphere, rarity, border, and the rolled artistic style)
    is stated in a "change" block. The preserve list is repeated in the
    Constraints section per OpenAI's anti-drift guidance.
    """
    facts = spec["character_facts"]
    direction = spec["direction_spec"]
    object_rule = direction["object_rule"]
    text_rule = direction["text_rule"]
    border_rule = direction["border_rule"]

    style_profile = STYLE_PROFILE_ALIASES.get(direction["style_profile"], direction["style_profile"])
    style_base = STYLE_BLOCK_BASE.get(style_profile, STYLE_BLOCK_BASE["trading_card_painterly"])
    atmosphere = _lookup_level_atmosphere(int(facts.get("level") or 1))
    rarity_visual = RARITY_VISUAL.get(str(facts.get("rarity") or "N"), RARITY_VISUAL["N"])

    class_name = facts.get("class_name") or "novice adventurer without a formal class"
    equipment = facts.get("equipment") or "simple basic clothing"
    background = facts.get("background") or "modest fantasy background"
    nickname_text = _quote_literal_text(text_rule["nameplate"]["text"])
    level_text = _quote_literal_text(text_rule["level_badge"]["text"])
    rarity_text = _quote_literal_text(text_rule["rarity_mark"]["text"])

    composition_rules_text = _join_rules(direction.get("composition_rules", []))
    forbidden_traits = _join_rules(
        list(facts.get("race_forbidden_traits", []))
        + list(facts.get("gender_forbidden_traits", []))
        + list(object_rule.get("forbidden_objects", []))
    )

    no_class_note = ""
    if direction["unlock_stage"] == "no_class":
        no_class_note = " Do not depict the character as any class, profession, or combat role."

    lines = [
        "Continue the character card series using the same character from the reference image. Re-render that character in a new artistic style and a new scene, but keep the character's identity exactly the same.",
        "",
        "Preserve from the reference image (do not redesign):",
        "- exact face: eyes, nose, mouth, jawline, facial proportions, skin texture",
        "- exact hairstyle, hair color, and hair length",
        "- race traits: ears, scales, fur, bark, slime translucency, wings, or other species-specific features visible in the reference",
        "- body proportions, build, height, and gender presentation",
        "- general overall body and skin color palette",
        "",
        "Change for this new card (re-render based on these new facts):",
        f"- artistic style: re-paint the same character in this new visual style → {style_base}",
        f"- class / profession: {class_name}.{no_class_note}",
        f"- clothing and equipment: {equipment} (replace whatever the reference image was wearing)",
        f"- held object: {object_rule['object_prompt']}; {object_rule['visibility_rule']}",
        f"- pose: {direction['pose_family']}",
        f"- expression: {direction['expression_family']}",
        f"- shot framing: {direction['shot_type']}, {direction['camera_angle']}, {direction['body_orientation']}",
        f"- background: {background}",
        f"- atmosphere and lighting: {direction['lighting']}, {direction['mood']}, {direction['color_palette']}, {atmosphere}",
        f"- rarity visual quality: {rarity_visual}",
        f"- card border: {border_rule['frame_prompt']}; {border_rule['accent_rule']}; {border_rule['layout_rule']}",
        "",
        "Composition requirements:",
        f"{composition_rules_text or 'single character; clear visual focus; face clearly visible; readable silhouette'}.",
        "",
        "Card text (must render exactly):",
        f"- top-left round metal badge contains exactly the text {level_text}, {text_rule['level_badge'].get('typography', 'bold readable digits')}.",
        f"- top-right rarity mark contains exactly the text {rarity_text}, {text_rule['rarity_mark'].get('typography', 'bold readable letters')}.",
        f"- bottom-center compact parchment scroll nameplate contains exactly the text {nickname_text}, {text_rule['nameplate'].get('typography', 'readable fantasy font')}; the scroll occupies only a small lower band of the card.",
        "",
        "Constraints:",
        "- The character is the same person as in the reference image, just at a new moment in their adventure — same face, same race, same body, same gender, same hair.",
        "- Do not redesign the character's face, race, body, or gender; only re-render in the new style with the new clothing, weapon, pose, and background described above.",
        "- Single character only; no extra characters, companions, animals, duplicated bodies, or obscured face.",
        f"- Avoid: {forbidden_traits or 'unintended race, gender, or object drift'}.",
        f"- Text rules: {_join_rules(text_rule['layout_constraints'])}.",
        "- Do not render any other letters, captions, labels, title text, subtitles, logos, signatures, watermarks, or UI text.",
        "- All characters must be fully clothed in tasteful fantasy attire suitable for an educational platform; no nudity, no exposed cleavage, no bare midriff, no revealing or skin-exposing armor.",
    ]
    return "\n".join(lines)


def render_prompt_spec_for_llm(spec: dict[str, Any]) -> str:
    facts = spec["character_facts"]
    direction = spec["direction_spec"]
    object_rule = direction["object_rule"]
    text_rule = direction["text_rule"]
    border_rule = direction["border_rule"]

    lines = [
        "Confirmed character facts:",
        f"- race: {facts.get('race') or 'unspecified fantasy race'}",
        f"- gender: {facts.get('gender') or 'unspecified'}",
        f"- class: {facts.get('class_name') or 'not yet unlocked'}",
        f"- combat style: {facts.get('combat_style')}",
        f"- equipment: {facts.get('equipment') or 'simple basic clothing'}",
        f"- background: {facts.get('background') or 'modest fantasy setting'}",
        f"- level: {facts.get('level')}",
        f"- rarity: {facts.get('rarity')}",
        f"- border material: {border_rule['material_name']}",
    ]
    if facts.get("race_mandatory_traits"):
        lines.extend([
            "",
            "Mandatory race traits:",
        ])
        lines.extend(f"- {rule}" for rule in facts["race_mandatory_traits"])
    if facts.get("race_forbidden_traits"):
        lines.extend([
            "",
            "Forbidden race drift:",
        ])
        lines.extend(f"- {rule}" for rule in facts["race_forbidden_traits"])
    if facts.get("gender_mandatory_traits"):
        lines.extend([
            "",
            "Gender presentation rules:",
        ])
        lines.extend(f"- {rule}" for rule in facts["gender_mandatory_traits"])
    if facts.get("gender_forbidden_traits"):
        lines.extend([
            "",
            "Forbidden gender drift:",
        ])
        lines.extend(f"- {rule}" for rule in facts["gender_forbidden_traits"])
    if facts.get("conflict_rules"):
        lines.extend([
            "",
            "Conflict-resolution rules:",
        ])
        lines.extend(f"- {rule}" for rule in facts["conflict_rules"])
    lines.extend([
        "",
        "Visual direction:",
        f"- unlock stage: {direction['unlock_stage']}",
        f"- style profile: {direction['style_profile']}",
        f"- archetype: {direction['archetype']}",
        f"- shot type: {direction['shot_type']}",
        f"- camera angle: {direction['camera_angle']}",
        f"- body orientation: {direction['body_orientation']}",
        f"- pose: {direction['pose_family']}",
        f"- expression: {direction['expression_family']}",
    ])
    if direction.get("style_hint"):
        lines.append(f"- additional style hint: {direction['style_hint']}")
    if direction["unlock_stage"] == "no_class":
        lines.append("- do not describe the character as any class, profession, or combat role")
    lines.extend([
        "",
        "Composition requirements:",
    ])
    lines.extend(f"- {rule}" for rule in direction["composition_rules"])
    lines.extend([
        "",
        "Object rule:",
        f"- {object_rule['object_prompt']}",
        f"- {object_rule['visibility_rule']}",
        f"- forbidden: {', '.join(object_rule['forbidden_objects'])}",
        "",
        "Border rule:",
        f"- {border_rule['frame_prompt']}",
        f"- {border_rule['accent_rule']}",
        f"- {border_rule['layout_rule']}",
        "",
        "Card text rule:",
        "- render readable English card text in the image",
        (
            f"- bottom center compact parchment scroll nameplate containing only the nickname in a single line: "
            f"{text_rule['nameplate']['text'] or 'Student'}"
        ),
        f"- top left round level badge with number only: {text_rule['level_badge']['text']}",
        f"- top right rarity letter mark: {text_rule['rarity_mark']['text']}",
        "- the top-right rarity mark must contain letters only, with no extra words such as rarity",
        "- the level number must appear only in the top-left badge and must not be repeated in the bottom nameplate",
        "- the nickname must not be split, duplicated, or expanded into extra title text",
    ])
    lines.extend(f"- {rule}" for rule in text_rule["layout_constraints"])
    lines.extend(["", "Write one coherent English image prompt."])
    return "\n".join(lines)


def build_style_prefix(
    level: int,
    rarity: str,
    border: str = "bronze",
    style_profile: str | None = None,
) -> str:
    """Build a compatible style prefix for the current worker flow.

    This legacy entry point is kept because worker.py still calls it directly.
    For now, when no style_profile is provided, it defaults to the current
    collectible-card direction for compatibility.
    """
    profile = STYLE_PROFILE_ALIASES.get(style_profile or "trading_card_painterly", style_profile or "trading_card_painterly")
    base = STYLE_BLOCK_BASE.get(profile, STYLE_BLOCK_BASE["trading_card_painterly"])
    atmosphere = _lookup_level_atmosphere(level)
    visual = RARITY_VISUAL.get(rarity, RARITY_VISUAL["N"])
    border_rule = build_border_rule(border=border, rarity=rarity)
    return f"{base}, {atmosphere}, {visual}, {border_rule['frame_prompt']}, {border_rule['accent_rule']}."


def build_structured_description(
    card_config: dict[str, Any],
    learning_data: dict[str, Any],
    student_nickname: str = "",
    attribute_metadata: dict[str, Any] | None = None,
    rng_seed: int | None = None,
    style_hint: str | None = None,
) -> str:
    """Build a direct cloud-ready prompt string for gpt-image-2.

    This wrapper keeps the original function signature, but unlike the legacy
    prompt_builder.py version, it does not ask another LLM to rewrite the spec.
    """
    spec = build_prompt_spec(
        card_config=card_config,
        learning_data=learning_data,
        student_nickname=student_nickname,
        attribute_metadata=attribute_metadata,
        rng_seed=rng_seed,
        style_hint=style_hint,
    )
    return render_prompt_spec_for_cloud_image(spec)
