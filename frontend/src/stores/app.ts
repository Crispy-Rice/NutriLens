import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ApiError, fetchConfig, fetchHealth } from '@/api/client'
import type { HealthResponse, PublicConfig } from '@/types/api'

/**
 * App-wide runtime state: the server's public config (upload limits, mode
 * list, disclaimer text) and the health snapshot. Both come from the backend
 * so nothing about limits is hardcoded in the UI.
 */
export const useAppStore = defineStore('app', () => {
  const config = ref<PublicConfig | null>(null)
  const health = ref<HealthResponse | null>(null)
  const loading = ref(false)
  const error = ref<ApiError | null>(null)

  const ready = computed(() => config.value !== null)
  const demoMode = computed(() => config.value?.demo_mode ?? health.value?.demo_mode ?? false)
  const disclaimer = computed(() => config.value?.disclaimer ?? '')
  const privacyNote = computed(() => config.value?.privacy_note ?? '')
  const modes = computed(() => config.value?.modes ?? [])
  const backendReachable = computed(() => health.value !== null)

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const [cfg, h] = await Promise.all([fetchConfig(), fetchHealth()])
      config.value = cfg
      health.value = h
    } catch (err) {
      error.value = err instanceof ApiError ? err : null
      config.value = null
      health.value = null
    } finally {
      loading.value = false
    }
  }

  return {
    config,
    health,
    loading,
    error,
    ready,
    demoMode,
    disclaimer,
    privacyNote,
    modes,
    backendReachable,
    load,
  }
})
