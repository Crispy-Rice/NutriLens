/**
 * Client-side image compression.
 *
 * Two reasons this matters: it cuts upload failures on slow connections, and
 * it keeps a 12MP phone photo from becoming a multi-megabyte request. The
 * backend re-validates and re-scales regardless — this is a courtesy to the
 * network, not a security boundary.
 */

export interface CompressionResult {
  blob: Blob
  width: number
  height: number
  originalBytes: number
  bytes: number
  /** False when the original was already small enough and we sent it as-is. */
  compressed: boolean
}

/** Refuse absurd sources outright rather than trying to decode them. */
export const MAX_SOURCE_BYTES = 40 * 1024 * 1024

export const ACCEPTED_MIME_TYPES = ['image/jpeg', 'image/png', 'image/webp']

export class ImagePrepareError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ImagePrepareError'
  }
}

interface LoadedSource {
  source: ImageBitmap | HTMLImageElement
  width: number
  height: number
  release: () => void
}

function loadImageElement(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new ImagePrepareError('这张图片无法读取，可能已损坏。'))
    img.src = url
  })
}

/**
 * Decode the file to something drawable.
 *
 * `imageOrientation: 'from-image'` makes the browser apply EXIF rotation, so
 * phone photos don't end up sideways once the EXIF is later stripped. The
 * `<img>` fallback gets the same behaviour from the default
 * `image-orientation: from-image` CSS.
 */
async function loadSource(file: File): Promise<LoadedSource> {
  if (typeof createImageBitmap === 'function') {
    try {
      const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
      return {
        source: bitmap,
        width: bitmap.width,
        height: bitmap.height,
        release: () => bitmap.close(),
      }
    } catch {
      // Older browsers reject the options bag; fall through to the <img> path.
    }
  }

  const url = URL.createObjectURL(file)
  try {
    const img = await loadImageElement(url)
    if (!img.naturalWidth || !img.naturalHeight) {
      throw new ImagePrepareError('这张图片没有可显示的尺寸，可能已损坏。')
    }
    return {
      source: img,
      width: img.naturalWidth,
      height: img.naturalHeight,
      release: () => URL.revokeObjectURL(url),
    }
  } catch (err) {
    URL.revokeObjectURL(url)
    throw err instanceof ImagePrepareError
      ? err
      : new ImagePrepareError('这张图片无法读取，可能已损坏。')
  }
}

function canvasToBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) resolve(blob)
        else reject(new ImagePrepareError('图片压缩失败，请换一张图片重试。'))
      },
      'image/jpeg',
      quality,
    )
  })
}

function drawToCanvas(
  source: ImageBitmap | HTMLImageElement,
  width: number,
  height: number,
): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new ImagePrepareError('当前浏览器不支持图片处理，请更换浏览器后重试。')
  // Transparent PNGs would otherwise composite onto black and look wrong in
  // the preview, so lay down white first.
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, width, height)
  ctx.drawImage(source, 0, 0, width, height)
  return canvas
}

export function validateSourceFile(file: File): void {
  if (file.size === 0) {
    throw new ImagePrepareError('这个文件是空的，请重新选择。')
  }
  if (file.size > MAX_SOURCE_BYTES) {
    throw new ImagePrepareError(
      `图片文件过大（${(file.size / 1024 / 1024).toFixed(1)} MB），请选择 40 MB 以内的图片。`,
    )
  }
  // Some mobile pickers report an empty type; let the decoder be the judge.
  if (file.type && !ACCEPTED_MIME_TYPES.includes(file.type)) {
    throw new ImagePrepareError('请上传 JPG、PNG 或 WebP 格式的图片。')
  }
}

export async function compressImage(
  file: File,
  maxEdge: number,
  quality = 0.8,
): Promise<CompressionResult> {
  validateSourceFile(file)

  const loaded = await loadSource(file)
  try {
    const { width, height } = loaded
    const longest = Math.max(width, height)
    const scale = longest > maxEdge ? maxEdge / longest : 1
    const targetW = Math.max(1, Math.round(width * scale))
    const targetH = Math.max(1, Math.round(height * scale))

    // Already small in both dimensions and bytes: re-encoding would only
    // inflate a tidy PNG into a bigger JPEG, so send the original.
    const needsResize = scale < 1
    const alreadySmallEnough = !needsResize && file.size <= 1024 * 1024
    if (alreadySmallEnough) {
      return {
        blob: file,
        width,
        height,
        originalBytes: file.size,
        bytes: file.size,
        compressed: false,
      }
    }

    const canvas = drawToCanvas(loaded.source, targetW, targetH)
    let blob = await canvasToBlob(canvas, quality)

    // A heavily compressible PNG can still come out smaller untouched.
    if (!needsResize && blob.size >= file.size) {
      return {
        blob: file,
        width,
        height,
        originalBytes: file.size,
        bytes: file.size,
        compressed: false,
      }
    }

    // If we hit the ceiling and the result is still large, take one cheaper
    // pass before giving up on quality.
    if (blob.size > 3 * 1024 * 1024 && quality > 0.6) {
      blob = await canvasToBlob(canvas, 0.6)
    }

    return {
      blob,
      width: targetW,
      height: targetH,
      originalBytes: file.size,
      bytes: blob.size,
      compressed: true,
    }
  } finally {
    loaded.release()
  }
}
