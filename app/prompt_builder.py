"""RPG 屬性映射表與 prompt 組裝邏輯。

將 card_config 中「已解鎖」的 RPG 屬性轉為英文描述；
未解鎖的屬性給予 LLM 創意指引，讓每次生成各有不同。
"""

# ---------------------------------------------------------------------------
# 映射表
# ---------------------------------------------------------------------------

RACE_MAP: dict[str, str] = {
    "elf": "an Elf with pointed ears and ethereal features",
    "human": "a Human with balanced features",
    "orc": "an Orc with tusks and muscular green-tinted skin",
    "dwarf": "a Dwarf with a stout build and thick beard",
    "dragon": "a Dragonborn with scaled skin and draconic features",
    "pixie": "a tiny Pixie with delicate wings and glowing aura",
    "plant": "a Plant creature with bark-like skin and leaf hair",
    "slime": "a Slime humanoid with translucent gelatinous body",
}

GENDER_MAP: dict[str, str] = {
    "male": "male",
    "female": "female",
    "neutral": "androgynous",
}

CLASS_MAP: dict[str, str] = {
    "archmage": "an Archmage radiating powerful arcane energy",
    "paladin": "a Paladin in shining holy armor",
    "ranger": "a Ranger in woodland attire",
    "assassin": "an Assassin cloaked in shadows",
    "priest": "a Priest with divine aura",
    "mage": "a Mage in enchanted robes",
    "warrior": "a Warrior in battle armor",
    "archer": "an Archer in light leather armor",
    "militia": "a Militia member in simple padded armor",
    "apprentice": "an Apprentice in plain robes",
    "farmer": "a Farmer in humble peasant clothes",
}

BODY_MAP: dict[str, str] = {
    "muscular": "muscular and well-built physique",
    "standard": "average athletic build",
    "slim": "slender and lean frame",
}

EQUIPMENT_MAP: dict[str, str] = {
    "legendary": "wearing legendary ornate armor with intricate golden engravings and gemstones",
    "fine": "wearing well-crafted polished armor with decorative elements",
    "common": "wearing standard functional armor in decent condition",
    "crude": "wearing crudely made armor with visible rough patches",
    "broken": "wearing tattered and broken armor held together with rope",
}

WEAPON_QUALITY_MAP: dict[str, str] = {
    "artifact": "legendary glowing artifact-tier",
    "fine": "finely crafted",
    "common": "standard",
    "crude": "crude and worn",
    "primitive": "primitive makeshift",
}

WEAPON_TYPE_MAP: dict[str, str] = {
    "sword": "longsword",
    "shield": "kite shield",
    "staff": "magical staff with glowing crystal",
    "spellbook": "ancient spellbook with arcane symbols",
    "bow": "longbow",
    "dagger": "twin daggers",
    "mace": "war mace",
    "spear": "battle spear",
    "short_sword": "short sword",
    "club": "wooden club",
    "wooden_stick": "simple wooden stick",
    "stone": "crude stone weapon",
}

BACKGROUND_MAP: dict[str, str] = {
    "palace_throne": "inside a grand palace throne room with golden pillars and red carpet",
    "dragon_lair": "in a dragon's lair surrounded by treasure and glowing crystals",
    "sky_city": "on a floating sky city with clouds and celestial architecture",
    "castle": "in a medieval stone castle with banners and torches",
    "magic_tower": "atop a wizard's tower with arcane circles and floating books",
    "town": "in a bustling medieval town square",
    "market": "at a lively market with merchant stalls",
    "village": "in a quiet rural village with thatched-roof cottages",
    "wilderness": "in an open wilderness with windswept grass",
    "ruins": "among crumbling ancient ruins overgrown with weeds",
}

EXPRESSION_MAP: dict[str, str] = {
    "regal": "with a regal commanding gaze",
    "passionate": "with an intense passionate expression",
    "confident": "with a confident determined look",
    "calm": "with a calm serene expression",
    "weary": "with a weary exhausted expression",
}

POSE_MAP: dict[str, str] = {
    "charging": "charging forward in a dynamic action pose",
    "battle_ready": "standing battle-ready with weapon drawn",
    "standing": "standing upright in a neutral pose",
    "crouching": "crouching low with a guarded stance",
}

BORDER_MAP: dict[str, str] = {
    "copper": "muted earthy tones, humble atmosphere",
    "silver": "cool silver moonlit tones, refined atmosphere",
    "gold": "warm golden radiance, majestic epic atmosphere",
}

# ---------------------------------------------------------------------------
# LV 氛圍表 + 稀有度視覺品質表（好修改的 config 結構）
# ---------------------------------------------------------------------------

# (level_min, level_max, atmosphere_description)
LEVEL_ATMOSPHERE: list[tuple[int, int, str]] = [
    (1,  25,  "soft muted tones, humble rustic atmosphere"),
    (26, 50,  "vivid colors, adventurous atmosphere"),
    (51, 75,  "dramatic lighting, heroic atmosphere"),
    (76, 100, "epic cinematic lighting, legendary atmosphere"),
]

RARITY_VISUAL: dict[str, str] = {
    "N":   "simple clean lines, minimal decoration",
    "R":   "decent detail, subtle glow effects",
    "SR":  "rich detail, magical particle effects, ornate decorations",
    "SSR": "highly detailed, radiant aura, intricate golden engravings, masterpiece",
    "UR":  "ultra detailed, divine glow, ethereal particle effects, legendary ornate decorations, masterpiece, best quality",
}

# ---------------------------------------------------------------------------
# 內部輔助函式
# ---------------------------------------------------------------------------

def _map(mapping: dict, key: str | None) -> str | None:
    """查表轉換。找不到 key 時以 'a fantasy {key}' 作為 fallback，讓 LLM 自行詮釋。"""
    if not key:
        return None
    return mapping.get(key, f"a fantasy {key}")


def _lookup_level_atmosphere(level: int) -> str:
    for lo, hi, desc in LEVEL_ATMOSPHERE:
        if lo <= level <= hi:
            return desc
    return "humble rustic atmosphere"


def _get_class_value(card_config: dict) -> str | None:
    return card_config.get("class") or card_config.get("class_") or None


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------

def build_style_prefix(level: int, rarity: str) -> str:
    """組裝 style prefix = 基底 + LV 氛圍 + 稀有度視覺品質。

    由 worker.py 取得後傳給 sd_runner.run_sd_cli()。
    """
    base = "Hearthstone-style fantasy card art, digital oil painting, warm dramatic lighting, rich saturated colors, painterly brushwork"
    atmosphere = _lookup_level_atmosphere(level)
    visual = RARITY_VISUAL.get(rarity, RARITY_VISUAL["N"])
    return f"{base}, {atmosphere}, {visual}."


def build_structured_description(
    card_config: dict,
    learning_data: dict,
    student_nickname: str = "",
) -> str:
    """組裝結構化描述，傳給 Ollama LLM。

    - 已解鎖屬性（card_config 中有值的）→ 明確描述
    - 未解鎖屬性（None 或未傳入的）→ 創意指引，讓 LLM 每次各有不同
    - Card Display → LV / 稀有度 / 暱稱的文字渲染指示（LLM 需原封保留）
    """
    level = int(card_config.get("level", 1))
    rarity = card_config.get("rarity", "N")
    border = card_config.get("border", "copper")

    # ── 已解鎖屬性 ────────────────────────────────────────────────
    confirmed: list[str] = []

    race_desc = _map(RACE_MAP, card_config.get("race"))
    if race_desc:
        confirmed.append(f"- Race: {race_desc}")

    gender_desc = _map(GENDER_MAP, card_config.get("gender"))
    if gender_desc:
        confirmed.append(f"- Gender: {gender_desc}")

    class_key = _get_class_value(card_config)
    class_desc = _map(CLASS_MAP, class_key)
    if class_desc:
        confirmed.append(f"- Class: {class_desc}")

    body_desc = _map(BODY_MAP, card_config.get("body"))
    if body_desc:
        confirmed.append(f"- Body Type: {body_desc}")

    equipment_desc = _map(EQUIPMENT_MAP, card_config.get("equipment"))
    if equipment_desc:
        confirmed.append(f"- Equipment: {equipment_desc}")

    weapon_quality = card_config.get("weapon_quality")
    weapon_type = card_config.get("weapon_type")
    if weapon_type and weapon_quality:
        wq = WEAPON_QUALITY_MAP.get(weapon_quality, weapon_quality)
        wt = WEAPON_TYPE_MAP.get(weapon_type, weapon_type)
        confirmed.append(f"- Weapon: {wt}, Quality: {wq}")
    elif weapon_type:
        wt = WEAPON_TYPE_MAP.get(weapon_type, weapon_type)
        confirmed.append(f"- Weapon: {wt}")

    background_desc = _map(BACKGROUND_MAP, card_config.get("background"))
    if background_desc:
        confirmed.append(f"- Background: {background_desc}")

    expression_desc = _map(EXPRESSION_MAP, card_config.get("expression"))
    if expression_desc:
        confirmed.append(f"- Expression: {expression_desc}")

    pose_desc = _map(POSE_MAP, card_config.get("pose"))
    if pose_desc:
        confirmed.append(f"- Pose: {pose_desc}")

    border_desc = BORDER_MAP.get(border, "muted earthy tones")
    confirmed.append(f"- Card border: {border} ({border_desc})")
    confirmed.append(f"- Character Level: {level}/100")

    # ── 未解鎖屬性的創意指引 ──────────────────────────────────────
    creative: list[str] = []

    if not class_key:
        creative.append(
            "Class/Profession: Not yet unlocked. Portray this character as a humble "
            "commoner or villager at the very start of their journey. Be creative and "
            "varied with their appearance — each generation should look and feel different."
        )
    if not card_config.get("equipment"):
        creative.append(
            "Equipment: Not yet unlocked. Dress them in simple everyday clothing "
            "(e.g. peasant tunic, worn fabric, plain cloth). No armor whatsoever."
        )
    if not weapon_type:
        creative.append(
            "Weapon: Not yet unlocked. They carry humble everyday items — "
            "a farming hoe, a broom, a walking stick, a bucket, or are empty-handed. "
            "Choose a different item each generation."
        )
    if not card_config.get("background"):
        creative.append(
            "Background: Not yet unlocked. Place them in a modest everyday setting — "
            "a small farm, a dirt road, a simple cottage, a meadow. "
            "Vary the specific scene each time."
        )
    if not card_config.get("expression"):
        creative.append(
            "Expression: Not yet unlocked. Choose a fitting expression for a beginner — "
            "curious, hopeful, nervous, or quietly determined. Vary it each generation."
        )
    if not card_config.get("pose"):
        creative.append(
            "Pose: Not yet unlocked. Choose a natural everyday pose — "
            "standing, looking around, mid-task, or resting. Vary it each time."
        )

    # ── Card Display 文字渲染指示 ────────────────────────────────
    display: list[str] = [
        f'- Display "LV {level}" in the top-left corner in bold pixel-style font.',
        f'- Display "{rarity}" in the top-right corner in bold pixel-style font.',
    ]
    if student_nickname:
        display.append(
            f'- Display the nickname "{student_nickname}" on a decorative scroll '
            f"banner at the bottom of the card in bold lettering."
        )

    # ── 組裝最終輸出 ──────────────────────────────────────────────
    out: list[str] = []

    out.append("=== Confirmed Attributes ===")
    out.append("\n".join(confirmed) if confirmed else "(none yet)")

    if creative:
        out.append("\n=== Creative Guidance for Unset Attributes ===")
        out.append(
            "These attributes are not yet unlocked. Use your creativity to fill them "
            "in vividly — each generation should feel unique even with the same base config."
        )
        for hint in creative:
            out.append(f"- {hint}")

    out.append("\n=== Card Display Instructions (preserve verbatim in your prompt) ===")
    out.extend(display)

    return "\n".join(out)
