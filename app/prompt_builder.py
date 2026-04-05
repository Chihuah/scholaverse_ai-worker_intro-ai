from __future__ import annotations

"""Prompt builder for fantasy RPG card generation.

This module now builds a structured prompt specification first, then renders
that spec into a stable text block for the LLM. Legacy public functions are
kept for compatibility with the current worker flow.
"""

import random
from typing import Any


RACE_MAP: dict[str, str] = {
    "elf": "elf",
    "human": "human",
    "orc": "orc",
    "dwarf": "dwarf",
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
    "monk": "martial_unarmed",
    "fighter": "martial_unarmed",
    "farmer": "civilian_novice",
}

EQUIPMENT_MAP: dict[str, str] = {
    "legendary": "legendary ornate armor with rich detail",
    "fine": "well-crafted gear with polished detail",
    "common": "standard functional gear",
    "crude": "crudely made gear with rough edges",
    "broken": "tattered and broken gear",
}

WEAPON_QUALITY_MAP: dict[str, str] = {
    "artifact": "legendary ornate",
    "fine": "finely crafted",
    "common": "standard",
    "crude": "crude and worn",
    "primitive": "primitive makeshift",
}

WEAPON_TYPE_MAP: dict[str, str] = {
    "sword": "longsword",
    "shield": "kite shield",
    "staff": "staff",
    "spellbook": "spellbook",
    "bow": "longbow",
    "dagger": "dagger",
    "mace": "war mace",
    "spear": "battle spear",
    "short_sword": "short sword",
    "club": "wooden club",
    "wooden_stick": "simple wooden stick",
    "stone": "crude stone weapon",
}

BACKGROUND_MAP: dict[str, str] = {
    "palace_throne": "grand palace throne room",
    "dragon_lair": "dragon lair with treasure and crystals",
    "sky_city": "floating sky city",
    "castle": "medieval stone castle",
    "magic_tower": "wizard tower filled with arcane details",
    "town": "bustling medieval town square",
    "market": "lively market street",
    "village": "quiet rural village",
    "wilderness": "open wilderness",
    "ruins": "ancient ruins",
}

EXPRESSION_MAP: dict[str, str] = {
    "regal": "regal commanding expression",
    "passionate": "intense passionate expression",
    "confident": "confident expression",
    "calm": "calm serene expression",
    "weary": "weary expression",
}

POSE_MAP: dict[str, str] = {
    "charging": "charging forward",
    "battle_ready": "battle-ready stance",
    "standing": "standing upright",
    "crouching": "crouching low",
}

LEVEL_ATMOSPHERE: list[tuple[int, int, str]] = [
    (1, 25, "soft muted tones, humble rustic atmosphere"),
    (26, 50, "vivid colors, adventurous atmosphere"),
    (51, 75, "dramatic lighting, heroic atmosphere"),
    (76, 100, "epic cinematic lighting, legendary atmosphere"),
]

RARITY_VISUAL: dict[str, str] = {
    "N": "simple clean lines, minimal decoration",
    "R": "decent detail, subtle glow effects",
    "SR": "rich detail, magical particle effects, ornate decorations",
    "SSR": "highly detailed, radiant aura, intricate golden engravings",
    "UR": "ultra detailed, divine glow, ethereal particle effects, ornate legendary decorations",
}

DEFAULT_STYLE_PROFILES: list[dict[str, Any]] = [
    {"name": "hearthstone_like_collectible_card", "weight": 1},
    {"name": "anime_fantasy_character_card", "weight": 1},
    {"name": "painterly_fantasy_card", "weight": 1},
]

STYLE_BLOCK_BASE: dict[str, str] = {
    "hearthstone_like_collectible_card": (
        "stylized high-fantasy collectible card illustration, rich fantasy card framing, "
        "heroic card-art presentation"
    ),
    "anime_fantasy_character_card": (
        "anime fantasy character card illustration, expressive fantasy hero design, "
        "polished character-card presentation"
    ),
    "painterly_fantasy_card": (
        "painterly fantasy card illustration, refined fantasy brushwork, "
        "elegant collectible card presentation"
    ),
}

CAMERA_ARCHETYPES: dict[str, dict[str, list[str]]] = {
    "hero_portrait": {
        "shot_type": ["upper-body portrait", "waist-up portrait", "three-quarter portrait"],
        "camera_angle": ["eye-level view", "slightly low-angle view", "slight three-quarter angle", "frontal centered view"],
        "body_orientation": [
            "facing forward",
            "turned slightly left",
            "turned slightly right",
            "body angled with head facing viewer",
        ],
        "pose_family": [
            "standing calmly",
            "confident presentation pose",
            "holding weapon at rest",
        ],
        "expression_family": [
            "calm and focused",
            "determined",
            "gentle and confident",
        ],
        "composition_rules": [
            "single character",
            "character is the clear visual focus",
            "clear character outline with visible facial features and clothing details",
            "face clearly visible",
            "reserved visual space for readable English card text",
        ],
    },
    "guardian_stance": {
        "shot_type": ["three-quarter portrait", "full-body heroic pose"],
        "camera_angle": ["eye-level view", "frontal centered view", "slightly low-angle view"],
        "body_orientation": ["facing forward", "body angled with head facing viewer"],
        "pose_family": ["ready-for-battle stance", "holding weapon at rest", "standing firmly"],
        "expression_family": ["serious heroic expression", "determined", "calm and focused"],
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
        "shot_type": ["three-quarter portrait", "full-body heroic pose"],
        "camera_angle": ["slight three-quarter angle", "slightly low-angle view"],
        "body_orientation": [
            "turned slightly left",
            "turned slightly right",
            "body angled with head facing viewer",
        ],
        "pose_family": [
            "casting magic",
            "raising one hand with magical energy",
            "staff held in a casting posture",
        ],
        "expression_family": ["mysterious", "calm and focused", "determined"],
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
        "shot_type": ["three-quarter portrait", "full-body heroic pose"],
        "camera_angle": ["slight three-quarter angle", "eye-level view"],
        "body_orientation": [
            "turned slightly left",
            "turned slightly right",
            "body angled with head facing viewer",
        ],
        "pose_family": [
            "ready-for-battle stance",
            "light forward-leaning stance",
            "weapon held in a swift poised manner",
        ],
        "expression_family": ["focused", "serious heroic expression", "confident"],
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
        "shot_type": ["close-up character card portrait", "upper-body portrait", "three-quarter portrait"],
        "camera_angle": ["slight three-quarter angle", "eye-level view", "slightly low-angle view", "frontal centered view"],
        "body_orientation": [
            "body angled with head facing viewer",
            "turned slightly left",
            "turned slightly right",
        ],
        "pose_family": ["standing calmly", "confident presentation pose", "graceful display pose"],
        "expression_family": ["gentle and confident", "mysterious", "calm and focused"],
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


def resolve_character_facts(
    card_config: dict[str, Any],
    learning_data: dict[str, Any],
    student_nickname: str = "",
    attribute_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del learning_data  # reserved for future use

    class_name = _metadata_value(attribute_metadata, "class") or _fallback_value(CLASS_MAP, _get_class_value(card_config))
    combat_style = resolve_combat_style(class_name, attribute_metadata)

    facts = {
        "race": _metadata_value(attribute_metadata, "race") or _fallback_value(RACE_MAP, card_config.get("race")),
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
    }
    return facts


def choose_style_profile(
    rarity: str,
    style_profiles: list[dict[str, Any]] | None = None,
    rng: random.Random | None = None,
) -> str:
    del rarity  # reserved for future weighting
    profiles = style_profiles or DEFAULT_STYLE_PROFILES
    weights = {item["name"]: float(item.get("weight", 1)) for item in profiles}
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
            "visibility_rule": "object clearly visible but not blocking the face",
            "forbidden_objects": [
                "ornate legendary weapon",
                "multiple weapons",
                "large floating props",
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
        "object_prompt": f"holding a {weapon_quality} {weapon_type}",
        "visibility_rule": "weapon clearly visible but not blocking the face",
        "forbidden_objects": [
            "multiple weapons",
            "extra companions",
            "oversized floating relics",
        ],
    }


def build_text_rule(student_nickname: str, level: int, rarity: str) -> dict[str, Any]:
    return {
        "text_mode": "render_in_image",
        "nameplate": {
            "text": student_nickname,
            "position": "bottom_center",
            "container": "parchment_scroll",
        },
        "level_badge": {
            "text": str(level),
            "position": "top_left",
            "container": "round_badge",
            "show_prefix": False,
        },
        "rarity_mark": {
            "text": rarity,
            "position": "top_right",
            "container": "plain_letter_mark",
        },
        "layout_constraints": [
            "all text must be readable",
            "text must not overlap the face",
            "text containers must feel integrated into the card design",
            "the bottom parchment nameplate must be compact and occupy only a small lower band of the card",
            "the bottom nameplate must contain only the nickname in a single line",
            "do not duplicate the nickname elsewhere in the card",
            "do not place extra large central text above the nameplate",
        ],
    }


def assemble_direction_spec(
    unlock_stage: str,
    style_profile: str,
    camera_spec: dict[str, Any],
    object_rule: dict[str, Any],
    text_rule: dict[str, Any],
) -> dict[str, Any]:
    direction = {
        "unlock_stage": unlock_stage,
        "style_profile": style_profile,
        **camera_spec,
        "object_rule": object_rule,
        "text_rule": text_rule,
    }
    return direction


def build_prompt_spec(
    card_config: dict[str, Any],
    learning_data: dict[str, Any],
    student_nickname: str = "",
    attribute_metadata: dict[str, Any] | None = None,
    rng_seed: int | None = None,
) -> dict[str, Any]:
    rng = random.Random(rng_seed) if rng_seed is not None else random.Random()
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
    direction_spec = assemble_direction_spec(
        unlock_stage=unlock_stage,
        style_profile=style_profile,
        camera_spec=camera_spec,
        object_rule=object_rule,
        text_rule=text_rule,
    )

    return {
        "schema_version": "v1",
        "character_facts": character_facts,
        "direction_spec": direction_spec,
    }


def render_prompt_spec_for_llm(spec: dict[str, Any]) -> str:
    facts = spec["character_facts"]
    direction = spec["direction_spec"]
    object_rule = direction["object_rule"]
    text_rule = direction["text_rule"]

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
    ]
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


def build_style_prefix(level: int, rarity: str, style_profile: str | None = None) -> str:
    """Build a compatible style prefix for the current worker flow.

    This legacy entry point is kept because worker.py still calls it directly.
    For now, when no style_profile is provided, it defaults to the current
    collectible-card direction for compatibility.
    """
    profile = style_profile or "hearthstone_like_collectible_card"
    base = STYLE_BLOCK_BASE.get(profile, STYLE_BLOCK_BASE["hearthstone_like_collectible_card"])
    atmosphere = _lookup_level_atmosphere(level)
    visual = RARITY_VISUAL.get(rarity, RARITY_VISUAL["N"])
    return f"{base}, {atmosphere}, {visual}."


def build_structured_description(
    card_config: dict[str, Any],
    learning_data: dict[str, Any],
    student_nickname: str = "",
    attribute_metadata: dict[str, Any] | None = None,
    rng_seed: int | None = None,
) -> str:
    """Legacy-compatible wrapper.

    Current worker.py still expects a string description for llm_service.
    Internally we now build a structured prompt spec first.
    """
    spec = build_prompt_spec(
        card_config=card_config,
        learning_data=learning_data,
        student_nickname=student_nickname,
        attribute_metadata=attribute_metadata,
        rng_seed=rng_seed,
    )
    return render_prompt_spec_for_llm(spec)
