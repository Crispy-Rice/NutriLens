import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useImageSelection } from '@/composables/useImageSelection'
import { useAppStore } from '@/stores/app'
import { useProfileStore } from '@/stores/profile'
import type { AnalysisResult, AnalysisMode, PartialField, StatusStage } from '@/types/api'
import { toApiError, type ApiError } from '@/api/client'
import { streamAnalyze } from '@/api/stream'

export type AnalysisPhase = 'idle' | 'preparing' | 'ready' | 'analyzing' | 'done' | 'error'

/**
 * Owns the single-shot analysis flow: the chosen images, the mode, and the
 * streaming/result state. Image handling itself lives in useImageSelection,
 * which the conversation composer shares.
 */
export const useAnalysisStore = defineStore('analysis', () => {
  const app = useAppStore()
  const profile = useProfileStore()

  const selection = useImageSelection({
    maxImages: () => app.config?.max_images ?? 4,
    maxTotalBytes: () => (app.config?.max_total_upload_mb ?? 20) * 1024 * 1024,
    edgeFor: (count) =>
      count <= 1
        ? (app.config?.max_image_edge ?? 1600)
        : (app.config?.multi_image_max_edge ?? 1024),
  })

  const mode = ref<AnalysisMode>('quick')
  const note = ref('')
  const phase = ref<AnalysisPhase>('idle')
  const error = ref<ApiError | null>(null)
  const stage = ref<StatusStage | null>(null)
  const statusMessage = ref('')
  const streamedText = ref('')
  // The dish name is written before the rest of the JSON, so the progress view
  // can name the dish instead of showing an empty placeholder.
  const streamedDishName = ref('')
  const result = ref<AnalysisResult | null>(null)

  let abortController: AbortController | null = null

  const hasImages = computed(() => selection.hasImages.value)
  const isAnalyzing = computed(() => phase.value === 'analyzing')
  const canAnalyze = computed(() => hasImages.value && !isAnalyzing.value)

  // The picker shows its own preparing state.
  const preparing = computed(() => phase.value === 'preparing' || selection.preparing.value)

  function clearResult(): void {
    error.value = null
    stage.value = null
    statusMessage.value = ''
    streamedText.value = ''
    streamedDishName.value = ''
    result.value = null
  }

  async function addFiles(files: File[]): Promise<void> {
    clearResult()
    phase.value = 'preparing'
    await selection.addFiles(files)
    phase.value = selection.images.value.length > 0 ? 'ready' : 'idle'
  }

  function removeImage(id: string): void {
    selection.removeImage(id)
    clearResult()
    phase.value = selection.images.value.length > 0 ? 'ready' : 'idle'
  }

  function clear(): void {
    abortController?.abort()
    abortController = null
    selection.clear()
    note.value = ''
    phase.value = 'idle'
    clearResult()
  }

  function setMode(next: AnalysisMode): void {
    mode.value = next
  }

  async function analyze(): Promise<void> {
    if (selection.images.value.length === 0) return

    abortController?.abort()
    abortController = new AbortController()

    clearResult()
    phase.value = 'analyzing'

    const form = new FormData()
    for (const item of selection.images.value) {
      // The server never sees the user's filename, only a neutral placeholder.
      form.append('files', item.compressed.blob, 'upload.jpg')
    }
    form.append('mode', mode.value)
    if (note.value.trim()) form.append('note', note.value.trim())
    // The profile is sent per request and never stored server-side.
    if (profile.payload) form.append('profile', profile.payload)

    try {
      await streamAnalyze(form, {
        signal: abortController.signal,
        onStatus: (event) => {
          stage.value = event.stage
          statusMessage.value = event.message
        },
        onPartial: (field: PartialField, text: string) => {
          if (field === 'dish_name') streamedDishName.value += text
          else streamedText.value += text
        },
        onResult: (payload) => {
          result.value = payload
        },
      })
      phase.value = result.value ? 'done' : 'error'
      if (!result.value) error.value = toApiError(new Error('missing result'))
    } catch (err) {
      if (abortController?.signal.aborted) {
        phase.value = hasImages.value ? 'ready' : 'idle'
        return
      }
      error.value = toApiError(err)
      phase.value = 'error'
    } finally {
      abortController = null
    }
  }

  function cancel(): void {
    abortController?.abort()
    abortController = null
  }

  return {
    images: selection.images,
    prepareError: selection.prepareError,
    sizeSummary: selection.sizeSummary,
    maxImages: selection.maxImages,
    preparing,
    mode,
    note,
    phase,
    error,
    stage,
    statusMessage,
    streamedText,
    streamedDishName,
    result,
    hasImages,
    isAnalyzing,
    canAnalyze,
    addFiles,
    removeImage,
    clear,
    clearResult,
    setMode,
    analyze,
    cancel,
  }
})
