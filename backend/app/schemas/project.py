from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ProjectStatus = Literal["uploaded", "analyzed", "processing", "awaiting_user", "completed", "failed", "cancelled"]
StageStatus = Literal["pending", "in_progress", "completed", "failed", "skipped", "blocked"]
QuestionSeverity = Literal["low", "medium", "high"]
QuestionKind = Literal["informative", "recommended", "blocking"]
RiskLevel = Literal["low", "medium", "high"]


class ArtifactReference(BaseModel):
    label: str
    path: str
    kind: str
    sha256: str | None = None
    size_bytes: int | None = None


class ProjectQuestion(BaseModel):
    code: str
    question: str
    reason: str
    severity: QuestionSeverity = "medium"
    kind: QuestionKind = "recommended"


class ProcessingStage(BaseModel):
    key: str
    label: str
    status: StageStatus = "pending"
    message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float | None = None


class DecisionRecord(BaseModel):
    stage_key: str
    action: str
    reason: str
    impact: str | None = None
    destructive: bool = False


class StageMetric(BaseModel):
    stage_key: str
    status: str
    started_at: datetime
    finished_at: datetime
    duration_ms: float
    memory_mb: float | None = None
    input_size_bytes: int | None = None


class PrintableScore(BaseModel):
    score: int = 0
    level: RiskLevel = "high"
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class MarketplaceAttribute(BaseModel):
    marketplace: str
    title: str
    category: str
    description: str
    short_description: str | None = None
    full_description: str | None = None
    product_context: str | None = None
    character_origin: str | None = None
    registration_attributes: list[dict[str, str]] = Field(default_factory=list)
    bullet_points: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    sku: str | None = None
    default_stock: int | None = None
    warranty: dict[str, Any] | None = None


class SalesProfileWarranty(BaseModel):
    type: str = "seller"
    duration: int = 1
    unit: str = "months"
    label: str = "1 mês — garantia do vendedor"


class SalesProfileVariation(BaseModel):
    sku: str
    name: str
    quantity: int = 1
    stock: int = 320
    price_brl: float
    description: str | None = None


class SalesProfileExtraPhoto(BaseModel):
    label: str
    path: str


class SalesProfile(BaseModel):
    pricing_version: str = "br-v4-ollama-marketplace-copy"
    copy_source: str = "deterministic"
    estimated_material_g: float = 0
    estimated_print_hours: float = 0
    estimated_base_cost_brl: float = 0
    suggested_price_50_margin_brl: float = 0
    reseller_price_brl: float = 0
    default_margin_percent: float = 50
    reseller_margin_percent: float = 25
    currency: str = "BRL"
    assumptions: list[str] = Field(default_factory=list)
    sales_tips: list[str] = Field(default_factory=list)
    marketplace_attributes: list[MarketplaceAttribute] = Field(default_factory=list)
    sku: str | None = None
    default_stock: int | None = None
    warranty: SalesProfileWarranty | None = None
    variations: list[SalesProfileVariation] = Field(default_factory=list)
    photo_label_overrides: dict[str, str] = Field(default_factory=dict)
    hidden_photo_paths: list[str] = Field(default_factory=list)
    extra_ad_photos: list[SalesProfileExtraPhoto] = Field(default_factory=list)


class InputFileRecord(BaseModel):
    name: str
    path: str
    suffix: str
    size_bytes: int
    sha256: str | None = None
    role: str = "primary"
    status: str = "ok"


class ParameterEquivalenceRecord(BaseModel):
    parameter: str
    source_value: Any = None
    target_value: Any = None
    status: Literal[
        "preserved_exactly",
        "preserved_approximately",
        "fallback_substitution",
        "discarded_incompatible",
        "requires_user_confirmation",
    ]
    note: str | None = None


class ExecutionSnapshot(BaseModel):
    inputs: list[InputFileRecord] = Field(default_factory=list)
    final_parameters: dict[str, Any] = Field(default_factory=dict)
    agent_outputs: list[dict[str, Any]] = Field(default_factory=list)
    prompts: dict[str, str] = Field(default_factory=dict)
    fallbacks: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactReference] = Field(default_factory=list)


class ProjectManifestModel(BaseModel):
    project_id: str
    project_name: str
    slug: str
    version: int
    created_at: datetime
    updated_at: datetime
    origin: str | None = None
    source_ecosystem: str
    input_formats: list[str] = Field(default_factory=list)
    pipeline_version: str
    agent_versions: dict[str, str] = Field(default_factory=dict)
    original_files: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    automatic_decisions: list[dict[str, Any]] = Field(default_factory=list)
    questions_asked: list[dict[str, Any]] = Field(default_factory=list)
    user_answers: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    snapshot: dict[str, Any] = Field(default_factory=dict)


class ProjectSummary(BaseModel):
    id: str
    name: str
    slug: str
    version: int
    status: ProjectStatus
    input_format: str
    source_ecosystem: str
    created_at: datetime
    updated_at: datetime
    preview_url: str | None = None
    printable_score: PrintableScore | None = None
    sales_profile: SalesProfile | None = None


class ProjectDetailResponse(ProjectSummary):
    storage_path: str
    original_filename: str
    size_bytes: int
    input_files: list[InputFileRecord] = Field(default_factory=list)
    requested_actions: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    questions_pending: list[ProjectQuestion] = Field(default_factory=list)
    blocking_questions: list[ProjectQuestion] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    processing_stages: list[ProcessingStage] = Field(default_factory=list)
    stage_metrics: list[StageMetric] = Field(default_factory=list)
    decisions: list[DecisionRecord] = Field(default_factory=list)
    artifacts: list[ArtifactReference] = Field(default_factory=list)
    previews: list[ArtifactReference] = Field(default_factory=list)
    reports: list[ArtifactReference] = Field(default_factory=list)
    logs: list[ArtifactReference] = Field(default_factory=list)
    bundles: list[ArtifactReference] = Field(default_factory=list)
    manifest: ProjectManifestModel | None = None
    snapshot: ExecutionSnapshot | None = None
    bambu_parameter_equivalence: list[ParameterEquivalenceRecord] = Field(default_factory=list)


class ProjectListResponse(BaseModel):
    items: list[ProjectSummary]
    total: int = 0
    page: int = 1
    per_page: int = 20
    pages: int = 1


class ImportUrlRequest(BaseModel):
    url: str
    project_name: str | None = None


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    target_material: str | None = None
    request_parameters: dict[str, Any] | None = None
    sales_profile: dict[str, Any] | None = None


class MaterialPreferences(BaseModel):
    use_case: Literal["decorative", "functional", "structural", "unknown"] = "unknown"
    thermal_resistance: bool | None = None
    outdoor_use: bool | None = None
    flexibility_required: bool | None = None
    desired_finish: str | None = None
    prioritize: Literal["aesthetics", "speed", "strength", "balanced"] = "balanced"


class ColorPreferences(BaseModel):
    preserve_original_colors: bool = True
    character_variant: str | None = None
    strategy: Literal["multicolor", "split_parts", "paint_after", "undecided", "monochrome"] = "undecided"
    notes: str | None = None


class HollowingPreferences(BaseModel):
    enabled: bool = False
    shell_thickness_mm: float = 2.0
    drain_holes: bool = True
    preserve_strength: bool = True


class TransformPreferences(BaseModel):
    reinforce_weak_regions: bool = False
    add_helper_base: bool = False
    simplify_microdetails: bool = False
    allow_destructive_changes: bool = False
    generate_alignment_pins: bool = False


class ProcessProjectRequest(BaseModel):
    repair_mesh: bool = True
    adapt_to_snapmaker: bool = True
    convert_from_bambu: bool = True
    scale_mode: Literal["keep", "fit_to_bed", "normalize_units", "ask"] = "keep"
    unit_mode: Literal["auto", "mm", "inch", "ask"] = "auto"
    hollowing: bool = False
    hollowing_preferences: HollowingPreferences = Field(default_factory=HollowingPreferences)
    transform_preferences: TransformPreferences = Field(default_factory=TransformPreferences)
    supports: Literal["auto", "disabled", "ask"] = "auto"
    target_material: str | None = None
    objective_preset: str = "quality"
    orientation_priority: Literal["aesthetics", "strength", "speed", "support_economy"] = "support_economy"
    target_nozzle_mm: float = 0.4
    material_preferences: MaterialPreferences = Field(default_factory=MaterialPreferences)
    color_preferences: ColorPreferences = Field(default_factory=ColorPreferences)
    notes: str | None = None


class ProjectCompareResponse(BaseModel):
    base_project_id: str
    target_project_id: str
    summary: list[str] = Field(default_factory=list)
    parameter_changes: dict[str, Any] = Field(default_factory=dict)
    printable_score_delta: dict[str, Any] = Field(default_factory=dict)
    artifacts_added: list[ArtifactReference] = Field(default_factory=list)


class ProjectBundleResponse(BaseModel):
    bundle: ArtifactReference


class ProjectPrintFileResponse(BaseModel):
    print_file: ArtifactReference
