/** Shared display helpers. Kept framework-free so they're trivial to test. */

export type Tone = 'primary' | 'accent' | 'danger' | 'neutral'

export interface ConfidenceBand {
  label: string
  tone: Tone
  /** True when the UI should prompt the user to confirm or re-shoot. */
  needsConfirmation: boolean
}

/**
 * Confidence is shown in named bands, never as a precise number, so the UI
 * doesn't imply a precision the model doesn't have. The band boundaries are
 * deliberately generous: we would rather nudge someone to double-check than
 * let a shaky guess look certain.
 */
export function confidenceBand(confidence: number, threshold = 0.55): ConfidenceBand {
  if (confidence >= 0.75) {
    return { label: '较有把握', tone: 'primary', needsConfirmation: false }
  }
  if (confidence >= threshold) {
    return { label: '大致确定', tone: 'accent', needsConfirmation: false }
  }
  return { label: '不太确定', tone: 'danger', needsConfirmation: true }
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

/** Null means "the model didn't say", which must not render as 0. */
export function formatNutrient(
  value: number | null | undefined,
  unit: string,
  digits = 0,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const rounded = digits > 0 ? value.toFixed(digits) : Math.round(value).toString()
  return `${rounded}${unit}`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Filesystem-safe filename fragment from a dish name. */
export function slugifyForFilename(text: string): string {
  const cleaned = text
    .trim()
    .replace(/[\\/:*?"<>|\s]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
  return cleaned.slice(0, 40) || 'analysis'
}
