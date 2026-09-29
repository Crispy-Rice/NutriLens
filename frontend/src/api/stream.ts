/**
 * SSE client for the two streaming endpoints.
 *
 * Why not `EventSource`: it can only issue GET requests with no body, and both
 * endpoints need to POST a multipart form. So we do it by hand — POST with
 * `fetch`, then read the response body as a stream and parse SSE frames.
 *
 * The frame parsing and error mapping are shared; only the event dispatch
 * differs between an analysis stream and a conversation turn.
 */

import { ApiError, apiBaseURL } from '@/api/client'
import type {
  AnalysisResult,
  ConversationMessage,
  PartialEvent,
  PartialField,
  StatusEvent,
} from '@/types/api'

export interface AnalysisStreamHandlers {
  signal?: AbortSignal
  onStatus?: (event: StatusEvent) => void
  onPartial?: (field: PartialField, text: string) => void
  onResult?: (result: AnalysisResult) => void
}

export interface TurnStreamHandlers {
  signal?: AbortSignal
  onStatus?: (event: StatusEvent) => void
  onPartial?: (field: PartialField, text: string) => void
  /** The stored assistant message for this turn. */
  onResult?: (message: ConversationMessage) => void
}

interface Frame {
  event: string
  data: string
}

/** Parse one SSE frame. Returns null for comments/heartbeats and empty frames. */
function parseFrame(raw: string): Frame | null {
  let event = 'message'
  const dataLines: string[] = []

  for (const line of raw.split('\n')) {
    // Lines starting with ':' are comments — we use them as keep-alive pings.
    if (!line || line.startsWith(':')) continue
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)

    if (field === 'event') event = value
    else if (field === 'data') dataLines.push(value)
  }

  if (dataLines.length === 0) return null
  return { event, data: dataLines.join('\n') }
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    // Non-JSON body; fall through to the generic error below.
  }

  const detail =
    typeof payload === 'object' && payload !== null && 'error' in payload
      ? (payload as { error: { code: string; message: string; hint?: string | null } }).error
      : null

  if (detail?.message) {
    return new ApiError({
      code: detail.code,
      message: detail.message,
      hint: detail.hint,
      status: response.status,
    })
  }

  return new ApiError({
    code: 'http_error',
    message: `服务返回了异常状态（${response.status}）。`,
    hint: '请稍后重试。',
    status: response.status,
  })
}

function parseErrorEvent(data: string): ApiError {
  try {
    const payload = JSON.parse(data) as {
      code?: string
      message?: string
      hint?: string | null
    }
    return new ApiError({
      code: payload.code ?? 'stream_error',
      message: payload.message ?? '处理过程中出现错误。',
      hint: payload.hint,
    })
  } catch {
    return new ApiError({
      code: 'stream_error',
      message: '处理过程中出现错误。',
      hint: '请稍后重试。',
    })
  }
}

/**
 * POST a multipart form and pump the SSE frames into `dispatch` until the
 * stream ends. `dispatch` returns an ApiError to abort with it, or null.
 */
async function postSse(
  url: string,
  form: FormData,
  signal: AbortSignal | undefined,
  dispatch: (frame: Frame) => ApiError | null,
): Promise<void> {
  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST',
      body: form,
      signal,
      headers: { Accept: 'text/event-stream' },
    })
  } catch (err) {
    if (signal?.aborted) throw err
    throw new ApiError({
      code: 'network_error',
      message: '无法连接到分析服务。',
      hint: '请确认后端已启动，并检查网络连接后重试。',
    })
  }

  if (!response.ok) throw await errorFromResponse(response)

  const reader = response.body?.getReader()
  if (!reader) {
    throw new ApiError({
      code: 'stream_unsupported',
      message: '当前浏览器不支持流式读取。',
      hint: '请更换较新的浏览器后重试。',
    })
  }

  const decoder = new TextDecoder()
  let buffer = ''
  // Held in an object rather than a plain `let` so TypeScript doesn't narrow it
  // to `null` and conclude the check below is unreachable — the assignment
  // happens inside a closure, which flow analysis can't see.
  const pending: { error: ApiError | null } = { error: null }

  const consume = (frame: Frame): void => {
    if (pending.error) return
    pending.error = dispatch(frame)
  }

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      // Normalise CRLF so frame splitting works against any server.
      buffer = buffer.replace(/\r\n/g, '\n')

      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const raw = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const frame = parseFrame(raw)
        if (frame) consume(frame)
        boundary = buffer.indexOf('\n\n')
      }
    }

    // A final frame may arrive without a trailing blank line.
    const tail = parseFrame(buffer)
    if (tail) consume(tail)
  } finally {
    reader.releaseLock()
  }

  if (pending.error) throw pending.error
}

/** Common status/partial/error handling shared by both stream types. */
function baseDispatch(
  handlers: {
    onStatus?: (e: StatusEvent) => void
    onPartial?: (field: PartialField, text: string) => void
  },
  onResultFrame: (data: string) => ApiError | null,
): (frame: Frame) => ApiError | null {
  return (frame) => {
    switch (frame.event) {
      case 'status':
        try {
          handlers.onStatus?.(JSON.parse(frame.data) as StatusEvent)
        } catch {
          // Cosmetic; keep the stream alive.
        }
        return null
      case 'partial':
        try {
          const payload = JSON.parse(frame.data) as PartialEvent
          handlers.onPartial?.(payload.field ?? 'reply', payload.text)
        } catch {
          // Partial text is best-effort.
        }
        return null
      case 'result':
        return onResultFrame(frame.data)
      case 'error':
        return parseErrorEvent(frame.data)
      default:
        return null
    }
  }
}

export async function streamAnalyze(
  form: FormData,
  handlers: AnalysisStreamHandlers,
): Promise<void> {
  const dispatch = baseDispatch(handlers, (data) => {
    try {
      handlers.onResult?.(JSON.parse(data) as AnalysisResult)
      return null
    } catch {
      return new ApiError({
        code: 'bad_result',
        message: '分析结果格式异常，无法解析。',
        hint: '请重试一次。如果持续失败，请反馈给我们。',
      })
    }
  })
  await postSse(`${apiBaseURL}/analyze/stream`, form, handlers.signal, dispatch)
}

export async function streamTurn(
  conversationId: string,
  form: FormData,
  handlers: TurnStreamHandlers,
): Promise<void> {
  const dispatch = baseDispatch(handlers, (data) => {
    try {
      handlers.onResult?.(JSON.parse(data) as ConversationMessage)
      return null
    } catch {
      return new ApiError({
        code: 'bad_result',
        message: '这一轮的回复格式异常，无法解析。',
        hint: '请重试一次。',
      })
    }
  })
  await postSse(
    `${apiBaseURL}/conversations/${conversationId}/turns/stream`,
    form,
    handlers.signal,
    dispatch,
  )
}
