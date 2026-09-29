<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ResultCard from '@/components/ResultCard.vue'
import { ApiError, deleteAnalysis, fetchAnalysis, toApiError } from '@/api/client'
import { useConfirm } from '@/composables/useConfirm'
import type { AnalysisResult } from '@/types/api'

/**
 * A stored analysis, in full.
 *
 * A page rather than a drawer: the content is long, and on a phone a route gives
 * real scrolling, refresh and back-button behaviour for free.
 */
const route = useRoute()
const router = useRouter()
const { confirm } = useConfirm()

const result = ref<AnalysisResult | null>(null)
const loading = ref(true)
const error = ref<ApiError | null>(null)

async function load(id: string): Promise<void> {
  loading.value = true
  error.value = null
  try {
    result.value = await fetchAnalysis(id)
  } catch (err) {
    error.value = toApiError(err)
    result.value = null
  } finally {
    loading.value = false
  }
}

function onUpdated(updated: AnalysisResult): void {
  result.value = updated
}

async function remove(): Promise<void> {
  if (!result.value) return
  const confirmed = await confirm({
    title: '删除这条记录？',
    subject: result.value.dish_name,
    message: '这条分析结果会从历史记录中永久移除，无法撤销。',
    details: ['原始照片本来就没有保存，删除记录不涉及图片。'],
    confirmLabel: '删除',
  })
  if (!confirmed) return

  try {
    await deleteAnalysis(result.value.id)
    await router.push({ name: 'history' })
  } catch (err) {
    error.value = toApiError(err)
  }
}

onMounted(() => load(String(route.params.id)))

// Support navigating between two detail pages without a remount.
watch(
  () => route.params.id,
  (id) => {
    if (id) void load(String(id))
  },
)
</script>

<template>
  <div class="page">
    <nav class="crumb" aria-label="返回">
      <RouterLink class="crumb__back" :to="{ name: 'history' }">
        ← 返回历史记录
      </RouterLink>
    </nav>

    <p v-if="loading" class="muted">正在读取…</p>

    <section v-else-if="error" class="card notice" role="alert">
      <h2 class="card__title">打不开这条记录</h2>
      <p>{{ error.message }}</p>
      <p v-if="error.hint" class="subtle">{{ error.hint }}</p>
      <RouterLink class="btn btn--primary" :to="{ name: 'history' }">
        回到历史记录
      </RouterLink>
    </section>

    <template v-else-if="result">
      <ResultCard :result="result" @updated="onUpdated" @restart="router.push('/')" />

      <div class="danger">
        <button class="btn btn--ghost danger__btn" type="button" @click="remove">
          删除这条记录
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.crumb {
  margin-bottom: var(--s-3);
}

.crumb__back {
  display: inline-flex;
  align-items: center;
  min-height: var(--tap-min);
  color: var(--c-primary);
  text-decoration: none;
  font-size: var(--fs-sm);
  font-weight: 600;
}

.crumb__back:hover {
  text-decoration: underline;
}

.notice {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--s-3);
  background: var(--c-surface-2);
}

.danger {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--s-4);
}

.danger__btn {
  color: var(--c-danger);
}

.danger__btn:hover {
  border-color: var(--c-danger);
  background: var(--c-danger-soft);
}

@media (max-width: 560px) {
  .danger {
    justify-content: stretch;
  }

  .danger__btn {
    width: 100%;
  }
}
</style>
