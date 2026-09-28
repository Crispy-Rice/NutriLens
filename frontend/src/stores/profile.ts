import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { AgeBand, ProfileSex, UserProfile } from '@/types/api'

/**
 * The user's dietary profile.
 *
 * Stored in localStorage and sent with each request; the server uses it for the
 * prompt and keeps nothing. That is why there is no API call in this store —
 * the profile never needs to reach the backend except as part of an analysis.
 *
 * Limits mirror schemas.py so the form can't build something the server would
 * reject.
 */

const STORAGE_KEY = 'nutrilens.profile.v1'

export const PROFILE_MAX_ITEMS = 20
export const PROFILE_MAX_ITEM_CHARS = 30
export const PROFILE_MAX_HEALTH_NOTES = 200

export const AGE_BAND_OPTIONS: { value: AgeBand; label: string }[] = [
  { value: '<18', label: '18 岁以下' },
  { value: '18-29', label: '18–29 岁' },
  { value: '30-39', label: '30–39 岁' },
  { value: '40-49', label: '40–49 岁' },
  { value: '50-59', label: '50–59 岁' },
  { value: '60+', label: '60 岁以上' },
]

export const SEX_OPTIONS: { value: ProfileSex; label: string }[] = [
  { value: 'female', label: '女' },
  { value: 'male', label: '男' },
  { value: 'other', label: '其他' },
  { value: 'unset', label: '不愿透露' },
]

export const DIETARY_PATTERN_SUGGESTIONS = [
  '无特别',
  '素食',
  '纯素',
  '清真',
  '低钠',
  '低糖',
  '低碳水',
]

export function emptyProfile(): UserProfile {
  return {
    allergies: [],
    avoidances: [],
    preferences: [],
    dietary_pattern: null,
    age_band: null,
    sex: null,
    health_notes: null,
  }
}

function cleanList(values: unknown): string[] {
  if (!Array.isArray(values)) return []
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of values) {
    const text = String(raw ?? '').trim().slice(0, PROFILE_MAX_ITEM_CHARS)
    if (!text || seen.has(text)) continue
    seen.add(text)
    out.push(text)
    if (out.length >= PROFILE_MAX_ITEMS) break
  }
  return out
}

function cleanScalar(value: unknown, max = PROFILE_MAX_ITEM_CHARS): string | null {
  if (value === null || value === undefined) return null
  const text = String(value).trim().slice(0, max)
  return text || null
}

/** Coerce anything into a valid profile, so corrupt storage can't break the app. */
export function sanitizeProfile(input: unknown): UserProfile {
  const raw = (typeof input === 'object' && input !== null ? input : {}) as Record<
    string,
    unknown
  >
  const ageBand = AGE_BAND_OPTIONS.some((o) => o.value === raw.age_band)
    ? (raw.age_band as AgeBand)
    : null
  const sex = SEX_OPTIONS.some((o) => o.value === raw.sex)
    ? (raw.sex as ProfileSex)
    : null

  return {
    allergies: cleanList(raw.allergies),
    avoidances: cleanList(raw.avoidances),
    preferences: cleanList(raw.preferences),
    dietary_pattern: cleanScalar(raw.dietary_pattern),
    age_band: ageBand,
    sex,
    health_notes: cleanScalar(raw.health_notes, PROFILE_MAX_HEALTH_NOTES),
  }
}

export function isProfileEmpty(profile: UserProfile): boolean {
  return (
    profile.allergies.length === 0 &&
    profile.avoidances.length === 0 &&
    profile.preferences.length === 0 &&
    !profile.dietary_pattern &&
    !profile.age_band &&
    !profile.sex &&
    !profile.health_notes
  )
}

export const useProfileStore = defineStore('profile', () => {
  const profile = ref<UserProfile>(emptyProfile())
  const loaded = ref(false)

  const isSet = computed(() => !isProfileEmpty(profile.value))

  /** Chips for the summary card, in a stable order. */
  const summary = computed(() => {
    const p = profile.value
    const rows: { label: string; values: string[] }[] = []
    if (p.allergies.length) rows.push({ label: '过敏原', values: p.allergies })
    if (p.avoidances.length) rows.push({ label: '忌口', values: p.avoidances })
    if (p.dietary_pattern) rows.push({ label: '饮食方式', values: [p.dietary_pattern] })
    if (p.preferences.length) rows.push({ label: '偏好', values: p.preferences })
    const meta: string[] = []
    if (p.age_band) meta.push(`${p.age_band} 岁`)
    if (p.sex) meta.push(SEX_OPTIONS.find((o) => o.value === p.sex)?.label ?? '')
    if (meta.length) rows.push({ label: '基本信息', values: meta.filter(Boolean) })
    if (p.health_notes) rows.push({ label: '希望留意', values: [p.health_notes] })
    return rows
  })

  /** JSON for the `profile` form field, or null when there's nothing to send. */
  const payload = computed(() => (isSet.value ? JSON.stringify(profile.value) : null))

  function load(): void {
    loaded.value = true
    if (typeof localStorage === 'undefined') return
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      profile.value = sanitizeProfile(JSON.parse(raw))
    } catch {
      // Corrupt or unreadable storage: start clean rather than fail.
      localStorage.removeItem(STORAGE_KEY)
      profile.value = emptyProfile()
    }
  }

  function save(next: UserProfile): void {
    const cleaned = sanitizeProfile(next)
    profile.value = cleaned
    if (typeof localStorage === 'undefined') return
    try {
      if (isProfileEmpty(cleaned)) localStorage.removeItem(STORAGE_KEY)
      else localStorage.setItem(STORAGE_KEY, JSON.stringify(cleaned))
    } catch {
      // Storage may be full or blocked (private mode); the in-memory copy stands.
    }
  }

  function clear(): void {
    profile.value = emptyProfile()
    if (typeof localStorage === 'undefined') return
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      // Nothing useful to do.
    }
  }

  return {
    profile,
    loaded,
    isSet,
    summary,
    payload,
    load,
    save,
    clear,
  }
})
