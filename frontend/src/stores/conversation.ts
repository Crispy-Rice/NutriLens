import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  createConversation,
  deleteConversation,
  fetchConversation,
  fetchConversations,
  toApiError,
  type ApiError,
} from '@/api/client'
import { streamTurn } from '@/api/stream'
import { useImageSelection } from '@/composables/useImageSelection'
import { useAppStore } from '@/stores/app'
import { useProfileStore } from '@/stores/profile'
import type {
  AnalysisMode,
  Conversation,
  ConversationMessage,
  ConversationSummary,
  PartialField,
  ProcessedImage,
  StatusStage,
} from '@/types/api'

/**
 * Multi-turn conversation state.
 *
 * The composer's attachments reuse the same image-selection logic as the
 * single-shot page, and the profile is attached per turn exactly as it is
 * there — never stored server-side.
 */
export const useConversationStore = defineStore('conversation', () => {
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

  const list = ref<ConversationSummary[]>([])
  const total = ref(0)
  const active = ref<Conversation | null>(null)
  const mode = ref<AnalysisMode>('detailed')

  const loadingList = ref(false)
  const loadingActive = ref(false)
  const listError = ref<ApiError | null>(null)
  const turnError = ref<ApiError | null>(null)

  const isResponding = ref(false)
  const stage = ref<StatusStage | null>(null)
  const statusMessage = ref('')
  const streamedText = ref('')
  const streamedDishName = ref('')
  const draft = ref('')

  let abort: AbortController | null = null

  const hasMessages = computed(() => (active.value?.messages.length ?? 0) > 0)
  const canSend = computed(
    () =>
      !isResponding.value &&
      (draft.value.trim().length > 0 || selection.hasImages.value),
  )

  /** A photo the user already acknowledged cannot be re-examined later. */
  const hasDiscardedPhotos = computed(() =>
    (active.value?.messages ?? []).some((m) => m.images.length > 0),
  )

  async function loadList(): Promise<void> {
    loadingList.value = true
    listError.value = null
    try {
      const page = await fetchConversations(50, 0)
      list.value = page.items
      total.value = page.total
    } catch (err) {
      listError.value = toApiError(err)
    } finally {
      loadingList.value = false
    }
  }

  async function open(id: string): Promise<void> {
    loadingActive.value = true
    turnError.value = null
    try {
      active.value = await fetchConversation(id)
    } catch (err) {
      turnError.value = toApiError(err)
      active.value = null
    } finally {
      loadingActive.value = false
    }
  }

  /**
   * Start a new conversation. The conversation is created empty and its first
   * turn is streamed separately, so the UI has a real id (and a live progress
   * indicator) from the first moment.
   */
  async function startNew(): Promise<string | null> {
    turnError.value = null
    try {
      const created = await createConversation(mode.value)
      active.value = {
        id: created.id,
        title: created.title,
        mode: created.mode,
        created_at: created.created_at,
        updated_at: created.updated_at,
        messages: [],
      }
      return created.id
    } catch (err) {
      turnError.value = toApiError(err)
      return null
    }
  }

  async function remove(id: string): Promise<void> {
    try {
      await deleteConversation(id)
      list.value = list.value.filter((item) => item.id !== id)
      total.value = Math.max(0, total.value - 1)
      if (active.value?.id === id) active.value = null
    } catch (err) {
      listError.value = toApiError(err)
    }
  }

  function reset(): void {
    cancel()
    selection.clear()
    draft.value = ''
    active.value = null
    turnError.value = null
    streamedText.value = ''
    streamedDishName.value = ''
  }

  function optimisticUserMessage(text: string): ConversationMessage {
    const conversation = active.value
    const nextSeq = (conversation?.messages.at(-1)?.seq ?? 0) + 1
    // Metadata mirrors what the server will store, so the thumbnail count is
    // right before the reply lands.
    const images: ProcessedImage[] = selection.images.value.map((item, index) => ({
      index,
      width: item.compressed.width,
      height: item.compressed.height,
      bytes: item.compressed.bytes,
      mime: 'image/jpeg',
      operations: [],
    }))

    return {
      id: `local-${Date.now()}-${nextSeq}`,
      seq: nextSeq,
      role: 'user',
      text: text.trim(),
      images,
      analysis: null,
      profile_used: false,
      created_at: new Date().toISOString(),
    }
  }

  async function sendTurn(): Promise<void> {
    const conversation = active.value
    if (!conversation || !canSend.value) return

    const text = draft.value.trim()
    const attachments = [...selection.images.value]

    turnError.value = null
    streamedText.value = ''
    streamedDishName.value = ''
    stage.value = null
    statusMessage.value = ''
    isResponding.value = true

    const optimistic = optimisticUserMessage(text)
    const wasFirstTurn = conversation.messages.length === 0
    conversation.messages.push(optimistic)

    const form = new FormData()
    for (const item of attachments) {
      form.append('files', item.compressed.blob, 'upload.jpg')
    }
    form.append('message', text)
    if (profile.payload) form.append('profile', profile.payload)

    // Clear the composer right away so it doesn't look stuck mid-flight.
    draft.value = ''
    selection.clear()

    abort = new AbortController()
    try {
      await streamTurn(conversation.id, form, {
        signal: abort.signal,
        onStatus: (event) => {
          stage.value = event.stage
          statusMessage.value = event.message
        },
        onPartial: (field: PartialField, chunk: string) => {
          if (field === 'dish_name') streamedDishName.value += chunk
          else streamedText.value += chunk
        },
        onResult: (message) => {
          conversation.messages.push(message)
          conversation.updated_at = message.created_at
          streamedText.value = ''
          streamedDishName.value = ''
        },
      })

      // The server names the conversation after its first dish; pull that back
      // so the header and list agree with what was stored.
      if (wasFirstTurn) {
        try {
          const fresh = await fetchConversation(conversation.id)
          active.value = fresh
        } catch {
          // The turn itself succeeded; a stale title is not worth surfacing.
        }
      }
    } catch (err) {
      if (abort?.signal.aborted) {
        // User cancelled: drop the optimistic bubble and give the text back.
        conversation.messages = conversation.messages.filter((m) => m.id !== optimistic.id)
        draft.value = text
        return
      }
      turnError.value = toApiError(err)
      conversation.messages = conversation.messages.filter((m) => m.id !== optimistic.id)
      draft.value = text
    } finally {
      isResponding.value = false
      abort = null
    }
  }

  function cancel(): void {
    abort?.abort()
    abort = null
  }

  return {
    // The composer's attachments are lifted to the top level so templates get
    // Pinia's automatic ref unwrapping instead of reaching through an object.
    images: selection.images,
    sizeSummary: selection.sizeSummary,
    maxImages: selection.maxImages,
    imagePrepareError: selection.prepareError,
    imagePreparing: selection.preparing,
    addImages: selection.addFiles,
    removeImage: selection.removeImage,

    list,
    total,
    active,
    mode,
    loadingList,
    loadingActive,
    listError,
    turnError,
    isResponding,
    stage,
    statusMessage,
    streamedText,
    streamedDishName,
    draft,
    hasMessages,
    canSend,
    hasDiscardedPhotos,
    loadList,
    open,
    startNew,
    remove,
    reset,
    sendTurn,
    cancel,
  }
})
