from pydantic import BaseModel, ConfigDict, Field


# === Request ===

class CardConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # 已解鎖屬性（僅有值才傳入，否則為 None）
    race: str | None = None
    gender: str | None = None
    class_: str | None = Field(default=None, alias="class")
    body: str | None = None
    equipment: str | None = None
    weapon_quality: str | None = None
    weapon_type: str | None = None
    background: str | None = None
    expression: str | None = None
    pose: str | None = None
    border: str = "copper"
    level: int = Field(ge=1, le=100)   # 1~100 完整等級
    rarity: str = "N"                   # N / R / SR / SSR / UR


class UnitScore(BaseModel):
    quiz: float | None = None
    homework: float | None = None
    completion: float | None = None


class LearningData(BaseModel):
    unit_scores: dict[str, UnitScore]
    overall_completion: float


class GenerateRequest(BaseModel):
    job_id: str
    card_id: int
    student_id: str  # 學號（純數字），作為 sd-cli seed
    student_nickname: str = "Student"  # 學生暱稱，會顯示在卡牌上
    card_config: CardConfig
    learning_data: LearningData
    style_hint: str = "16-bit pixel art, fantasy RPG character card"
    seed: int | None = None
    ollama_model_override: str | None = None
    callback_url: str
    # Cloud generation (Phase 1a) ----------------------------------------
    backend: str = "local"  # "local" | "cloud"
    cloud_model: str | None = None  # 覆寫預設模型（測試新模型 id 用）
    reference_card_id: int | None = None  # 預留 Phase 1b（image edit）


# === Response ===

class GenerateResponse(BaseModel):
    job_id: str
    status: str
    position: int
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    card_id: int
    status: str  # queued / processing / uploading / completed / failed
    position: int | None = None
    image_path: str | None = None
    thumbnail_path: str | None = None
    prompt: str | None = None
    final_prompt: str | None = None
    llm_model: str | None = None
    lora_used: str | None = None       # 實際使用的 LoRA tag（"none" 代表未使用）
    seed: int | None = None
    generated_at: str | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    gpu_available: bool
    ollama_available: bool
    sd_cli_available: bool
    queue_size: int
    current_job: str | None = None


# === Callback (送回 vm-web-server) ===

class GenerationCallback(BaseModel):
    job_id: str
    card_id: int
    status: str  # "completed" or "failed"
    image_path: str | None = None
    thumbnail_path: str | None = None
    generated_at: str | None = None
    prompt: str | None = None
    final_prompt: str | None = None
    llm_model: str | None = None
    lora_used: str | None = None
    seed: int | None = None
    error: str | None = None
    # Cloud generation (Phase 1a) ----------------------------------------
    backend_used: str = "local"            # 實際使用的後端
    cloud_model: str | None = None         # gpt-image-2 / null
    cloud_mode: str | None = None          # generate / edit / null
    cloud_quality: str | None = None       # low / medium / high / auto
    fallback_from_cloud: bool = False      # cloud 失敗回退本地時 True
    cloud_error: str | None = None         # fallback 時保留錯誤訊息
    reference_card_id: int | None = None   # Phase 1b 用


# === Queue Status ===

class QueueItem(BaseModel):
    job_id: str
    card_id: int
    student_id: str
    status: str         # queued / processing / uploading
    position: int       # 0=正在處理, 1+=排隊中
    created_at: str     # ISO format


class QueueResponse(BaseModel):
    current_job: QueueItem | None
    queued_jobs: list[QueueItem]
    queue_size: int