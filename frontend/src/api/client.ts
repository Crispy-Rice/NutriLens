import axios, { AxiosError } from 'axios'
import type {
  AnalysisMode,
  Conversation,
  ConversationPage,
  ConversationSummary,
  ErrorResponse,
  HealthResponse,
  HistoryPage,
  PublicConfig,
} from '@/types/api'

/**
 * In dev, requests go to `/api` and Vite proxies them to the backend, so the
 * browser sees a same-origin call and CORS never enters the picture. Setting
 * VITE_API_BASE points the app at an absolute backend URL instead, for when
 * the frontend is served separately.
 */
const baseURL = import.meta.env.VITE_API_BASE || '/api'

export const http = axios.create({
  baseURL,
  timeout: 120_000,
})

/** An error already shaped for display: a message plus an optional next step. */
export class ApiError extends Error {
  readonly code: string
  readonly hint: string | null
  readonly requestId: string | null
  readonly status: number | null

  constructor(opts: {
    code: string
    message: string
    hint?: string | null
    requestId?: string | null
    status?: number | null
  }) {
    super(opts.message)
    this.name = 'ApiError'
    this.code = opts.code
    this.hint = opts.hint ?? null
    this.requestId = opts.requestId ?? null
    this.status = opts.status ?? null
  }
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as ErrorResponse).error?.message === 'string'
  )
}

export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err

  if (err instanceof AxiosError) {
    // The backend always replies with ErrorResponse; trust it when present.
    if (isErrorResponse(err.response?.data)) {
      const detail = err.response.data.error
      return new ApiError({
        code: detail.code,
        message: detail.message,
        hint: detail.hint,
        requestId: detail.request_id,
        status: err.response?.status ?? null,
      })
    }
    if (err.code === 'ECONNABORTED') {
      return new ApiError({
        code: 'timeout',
        message: '请求超时了。',
        hint: '网络较慢或分析任务较重，请重试，或改用「快速识别」模式。',
      })
    }
    if (!err.response) {
      return new ApiError({
        code: 'network_error',
        message: '无法连接到分析服务。',
        hint: '请确认后端已启动，并检查网络连接后重试。',
      })
    }
    return new ApiError({
      code: 'http_error',
      message: `服务返回了异常状态（${err.response.status}）。`,
      hint: '请稍后重试。',
      status: err.response.status,
    })
  }

  return new ApiError({
    code: 'unknown_error',
    message: '出现了未知错误。',
    hint: '请刷新页面后重试。',
  })
}

export async function fetchHealth(): Promise<HealthResponse> {
  try {
    const { data } = await http.get<HealthResponse>('/health')
    return data
  } catch (err) {
    throw toApiError(err)
  }
}

export async function fetchConfig(): Promise<PublicConfig> {
  try {
    const { data } = await http.get<PublicConfig>('/config')
    return data
  } catch (err) {
    throw toApiError(err)
  }
}

export async function fetchHistory(limit = 20, offset = 0): Promise<HistoryPage> {
  try {
    const { data } = await http.get<HistoryPage>('/history', { params: { limit, offset } })
    return data
  } catch (err) {
    throw toApiError(err)
  }
}

export async function deleteAnalysis(id: string): Promise<void> {
  try {
    await http.delete(`/history/${id}`)
  } catch (err) {
    throw toApiError(err)
  }
}

/* --- conversations --- */

export async function createConversation(mode: AnalysisMode): Promise<ConversationSummary> {
  try {
    const { data } = await http.post<ConversationSummary>('/conversations', { mode })
    return data
  } catch (err) {
    throw toApiError(err)
  }
}

export async function fetchConversations(
  limit = 20,
  offset = 0,
): Promise<ConversationPage> {
  try {
    const { data } = await http.get<ConversationPage>('/conversations', {
      params: { limit, offset },
    })
    return data
  } catch (err) {
    throw toApiError(err)
  }
}

export async function fetchConversation(id: string): Promise<Conversation> {
  try {
    const { data } = await http.get<Conversation>(`/conversations/${id}`)
    return data
  } catch (err) {
    throw toApiError(err)
  }
}

export async function deleteConversation(id: string): Promise<void> {
  try {
    await http.delete(`/conversations/${id}`)
  } catch (err) {
    throw toApiError(err)
  }
}

export { baseURL as apiBaseURL }
