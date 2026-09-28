import { computed, ref } from 'vue'
import {
  compressImage,
  ImagePrepareError,
  validateSourceFile,
  type CompressionResult,
} from '@/composables/useImageCompress'

export interface SelectedImage {
  /** Local key for list rendering. */
  id: string
  originalFile: File
  compressed: CompressionResult
  previewUrl: string
  /** Which edge this blob was compressed for, so we know when to re-derive it. */
  edge: number
}

export interface ImageSelectionOptions {
  /** Max images allowed in one request; read reactively from server config. */
  maxImages: () => number
  /** Shared byte budget across the selection. */
  maxTotalBytes: () => number
  /** Edge to compress at for a given final image count. */
  edgeFor: (count: number) => number
}

/**
 * The pick-compress-preview lifecycle for a set of images.
 *
 * Shared by the single-shot analysis page and the conversation composer, which
 * need identical behaviour: cap the count, compress client-side, re-derive when
 * crossing between one and several images, and never leak object URLs.
 */
export function useImageSelection(options: ImageSelectionOptions) {
  const images = ref<SelectedImage[]>([])
  const prepareError = ref<string | null>(null)
  const preparing = ref(false)

  let localSeq = 0

  const hasImages = computed(() => images.value.length > 0)
  const maxImages = computed(() => options.maxImages())
  const canAddMore = computed(() => images.value.length < maxImages.value)

  const sizeSummary = computed(() => {
    if (images.value.length === 0) return null
    const bytes = images.value.reduce((sum, i) => sum + i.compressed.bytes, 0)
    const originalBytes = images.value.reduce((sum, i) => sum + i.compressed.originalBytes, 0)
    return {
      count: images.value.length,
      bytes,
      originalBytes,
      compressed: images.value.some((i) => i.compressed.compressed),
      savedPercent:
        originalBytes > bytes ? Math.round((1 - bytes / originalBytes) * 100) : 0,
      dimensions: images.value.map((i) => ({
        width: i.compressed.width,
        height: i.compressed.height,
      })),
    }
  })

  function releaseAll(): void {
    for (const item of images.value) URL.revokeObjectURL(item.previewUrl)
    images.value = []
  }

  async function recompressAll(edge: number): Promise<void> {
    for (const item of images.value) {
      if (item.edge === edge) continue
      try {
        const compressed = await compressImage(item.originalFile, edge)
        URL.revokeObjectURL(item.previewUrl)
        item.compressed = compressed
        item.previewUrl = URL.createObjectURL(compressed.blob)
        item.edge = edge
      } catch {
        // Keep the previous version rather than dropping the image.
      }
    }
  }

  async function addFiles(files: File[]): Promise<void> {
    prepareError.value = null
    if (files.length === 0) return

    const room = maxImages.value - images.value.length
    if (room <= 0) {
      prepareError.value = `一次最多上传 ${maxImages.value} 张图片。`
      return
    }

    const accepted = files.slice(0, room)
    if (files.length > room) {
      prepareError.value = `一次最多上传 ${maxImages.value} 张，已忽略多出的 ${
        files.length - room
      } 张。`
    }

    preparing.value = true
    try {
      for (const file of accepted) {
        try {
          validateSourceFile(file)
          const edge = options.edgeFor(images.value.length + 1)
          const compressed = await compressImage(file, edge)
          images.value.push({
            id: `img-${localSeq++}`,
            originalFile: file,
            compressed,
            previewUrl: URL.createObjectURL(compressed.blob),
            edge,
          })
        } catch (err) {
          prepareError.value =
            err instanceof ImagePrepareError ? err.message : '图片处理失败，请换一张重试。'
        }
      }

      if (
        images.value.reduce((sum, i) => sum + i.compressed.bytes, 0) >
        options.maxTotalBytes()
      ) {
        prepareError.value = '这批图片的总大小超过上限，请减少张数。'
      }

      // Crossing into multi-image means the earlier ones were compressed at the
      // larger edge; re-derive so the preview matches what actually gets sent.
      if (images.value.length > 1) await recompressAll(options.edgeFor(2))
    } finally {
      preparing.value = false
    }
  }

  function removeImage(id: string): void {
    const index = images.value.findIndex((i) => i.id === id)
    if (index === -1) return
    const [removed] = images.value.splice(index, 1)
    if (removed) URL.revokeObjectURL(removed.previewUrl)
    prepareError.value = null

    // Dropping back to a single image lets it use the full edge again.
    if (images.value.length === 1) void recompressAll(options.edgeFor(1))
  }

  function clear(): void {
    releaseAll()
    prepareError.value = null
  }

  return {
    images,
    prepareError,
    preparing,
    hasImages,
    maxImages,
    canAddMore,
    sizeSummary,
    addFiles,
    removeImage,
    clear,
    releaseAll,
  }
}
