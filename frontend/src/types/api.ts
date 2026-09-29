/**
 * Mirrors backend/app/schemas.py. Keep the two in sync by hand — the pair is
 * small and explicit, which beats a codegen step for a project this size.
 *
 * Note what is absent: there is no health score, grade or rating field, by
 * design. See the comment at the top of schemas.py.
 */

export type AnalysisMode = 'quick' | 'detailed'

export interface Nutrition {
  calories_kcal: number | null
  protein_g: number | null
  fat_g: number | null
  carbs_g: number | null
  fiber_g: number | null
  sugar_g: number | null
  sodium_mg: number | null
  basis: string
}

export interface Ingredient {
  name: string
  estimated_amount: string | null
  note: string | null
}

export interface ProcessedImage {
  /** Position in the uploaded set, so a thumbnail pairs with its record. */
  index: number
  width: number
  height: number
  bytes: number
  mime: string
  operations: string[]
}

export interface DishAnalysis {
  dish_name: string
  dish_name_alternatives: string[]
  confidence: number
  confidence_reason: string | null
  ingredients: Ingredient[]
  portion_estimate: string | null
  nutrition: Nutrition
  advice: string
  risk_notes: string[]
  uncertainty_notes: string[]
}

/**
 * One dimension of the meal as a whole.
 *
 * `level` is a quantity word (偏少 / 适中 / 偏多), never a quality word, and
 * must not be colour-coded — green/red styling would turn it into a grade.
 */
export interface MealAspect {
  label: string
  level: string | null
  note: string
}

export interface MealOverall {
  summary: string
  aspects: MealAspect[]
}

export interface AnalysisResult {
  id: string
  created_at: string
  mode: AnalysisMode
  dish_name: string
  dish_name_alternatives: string[]
  confidence: number
  confidence_reason: string | null
  ingredients: Ingredient[]
  portion_estimate: string | null
  nutrition: Nutrition
  /** Dimension-by-dimension view of the meal; null when not provided. */
  overall: MealOverall | null
  /** Other dishes seen in the same photos; empty for a single-dish meal. */
  additional_dishes: DishAnalysis[]
  advice: string
  risk_notes: string[]
  uncertainty_notes: string[]
  disclaimer: string
  degraded: boolean
  provider: string
  images: ProcessedImage[]
  /** True when a user profile informed this result. Contents are never stored. */
  profile_used: boolean
  /** True once the user has corrected the recognition by hand. */
  edited: boolean
}

export interface AnalysisSummary {
  id: string
  created_at: string
  mode: AnalysisMode
  dish_name: string
  confidence: number
  calories_kcal: number | null
  /** True when the user corrected this record by hand. */
  edited: boolean
}

export interface HistoryPage {
  items: AnalysisSummary[]
  total: number
  limit: number
  offset: number
}

export interface ModeOption {
  value: AnalysisMode
  label: string
  description: string
}

export interface PublicConfig {
  app_name: string
  version: string
  demo_mode: boolean
  max_upload_mb: number
  max_image_edge: number
  max_images: number
  /** Smaller edge applied when more than one image is uploaded. */
  multi_image_max_edge: number
  max_total_upload_mb: number
  allowed_mime_types: string[]
  modes: ModeOption[]
  low_confidence_threshold: number
  disclaimer: string
  privacy_note: string
}

export interface HealthResponse {
  status: 'ok' | 'degraded'
  version: string
  provider: string
  llm_configured: boolean
  demo_mode: boolean
  llm_model: string
  database: string
}

/* --- conversations --- */

export type MessageRole = 'user' | 'assistant'

export interface ConversationMessage {
  id: string
  seq: number
  role: MessageRole
  text: string
  /** Metadata only — the photos themselves are gone. */
  images: ProcessedImage[]
  /** Present when the turn produced a structured analysis. */
  analysis: AnalysisResult | null
  /** True when a profile informed this turn. Contents are never stored. */
  profile_used: boolean
  created_at: string
}

export interface Conversation {
  id: string
  title: string
  mode: AnalysisMode
  created_at: string
  updated_at: string
  messages: ConversationMessage[]
}

export interface ConversationSummary {
  id: string
  title: string
  mode: AnalysisMode
  created_at: string
  updated_at: string
  turn_count: number
}

export interface ConversationPage {
  items: ConversationSummary[]
  total: number
  limit: number
  offset: number
}

/* --- user profile ---
 *
 * Mirrors UserProfile in schemas.py. Deliberately no body metrics or diagnosed
 * conditions: the product promises not to grade or diagnose, and structured
 * height/weight would invite exactly that. The profile lives in this browser
 * only and is never stored by the server.
 */

export type AgeBand = '<18' | '18-29' | '30-39' | '40-49' | '50-59' | '60+'
export type ProfileSex = 'female' | 'male' | 'other' | 'unset'

export interface UserProfile {
  allergies: string[]
  avoidances: string[]
  preferences: string[]
  dietary_pattern: string | null
  age_band: AgeBand | null
  sex: ProfileSex | null
  /** Free text; used to filter ingredients, never as a basis for a diagnosis. */
  health_notes: string | null
}

export interface ErrorDetail {
  code: string
  message: string
  hint: string | null
  request_id: string | null
}

export interface ErrorResponse {
  error: ErrorDetail
}

/* --- SSE payloads --- */

export type StatusStage =
  | 'received'
  | 'validating'
  | 'preprocessing'
  | 'calling_model'
  | 'parsing'
  | 'done'

export interface StatusEvent {
  stage: StatusStage
  message: string
}

/** Which part of the reply a partial chunk belongs to. */
export type PartialField = 'dish_name' | 'advice' | 'reply'

export interface PartialEvent {
  field: PartialField
  text: string
}
