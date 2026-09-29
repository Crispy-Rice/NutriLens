<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError, deleteAnalysis, fetchHistory } from '@/api/client'
import { useConfirm } from '@/composables/useConfirm'
import { useAppStore } from '@/stores/app'
import type { AnalysisSummary } from '@/types/api'
import { confidenceBand, formatDateTime, formatNutrient } from '@/utils/format'

const app = useAppStore()
const { confirm } = useConfirm()
const items = ref<AnalysisSummary[]>([])
const total = ref(0)
const loading = ref(true)
const error = ref<ApiError | null>(null)
const deletingId = ref<string | null>(null)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const page = await fetchHistory(50, 0)
    items.value = page.items
    total.value = page.total
  } catch (err) {
    error.value = err as ApiError
  } finally {
    loading.value = false
  }
}

async function remove(item: AnalysisSummary): Promise<void> {
  const confirmed = await confirm({
    title: '删除这条记录？',
    subject: item.dish_name,
    message: '这条分析结果会从历史记录中永久移除，无法撤销。',
    details: [
      `${formatDateTime(item.created_at)} · ${
        item.mode === 'detailed' ? '详细分析' : '快速识别'
      }`,
      '原始照片本来就没有保存，删除记录不涉及图片。',
    ],
    confirmLabel: '删除',
  })
  if (!confirmed) return

  deletingId.value = item.id
  try {
    await deleteAnalysis(item.id)
    items.value = items.value.filter((i) => i.id !== item.id)
    total.value = Math.max(0, total.value - 1)
  } catch (err) {
    error.value = err as ApiError
  } finally {
    deletingId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <header class="head">
      <div>
        <h1 class="head__title">历史记录</h1>
        <p class="subtle">
          共 {{ total }} 条。这里只保存结构化的分析结果，不含你的原始图片。
        </p>
      </div>
      <button class="btn btn--ghost" type="button" :disabled="loading" @click="load">
        刷新
      </button>
    </header>

    <p v-if="loading" class="muted">正在读取…</p>

    <section v-else-if="error" class="card notice" role="alert">
      <h2 class="card__title">读取失败</h2>
      <p>{{ error.message }}</p>
      <p v-if="error.hint" class="subtle">{{ error.hint }}</p>
    </section>

    <section v-else-if="items.length === 0" class="card empty">
      <h2 class="card__title">还没有分析记录</h2>
      <p class="muted">回到「识别」页上传一张食物照片，结果会自动记录在这里。</p>
      <RouterLink class="btn btn--primary" to="/">去识别</RouterLink>
    </section>

    <ul v-else class="list">
      <li v-for="item in items" :key="item.id" class="row-item">
        <!-- The whole row opens the detail page. Delete sits outside the link,
             because a button nested in an anchor is invalid and would swallow
             the tap. -->
        <RouterLink class="row-item__link" :to="{ name: 'history-detail', params: { id: item.id } }">
          <div class="row-item__main">
            <p class="row-item__dish">{{ item.dish_name }}</p>
            <p class="row-item__meta subtle">
              {{ formatDateTime(item.created_at) }} ·
              {{ item.mode === 'detailed' ? '详细分析' : '快速识别' }}
            </p>
          </div>

          <div class="row-item__stats">
            <span v-if="item.edited" class="badge badge--accent">已修正</span>
            <span class="badge" :class="`badge--${confidenceBand(item.confidence, app.config?.low_confidence_threshold).tone}`">
              {{ confidenceBand(item.confidence, app.config?.low_confidence_threshold).label }}
            </span>
            <span class="row-item__kcal mono">
              {{ formatNutrient(item.calories_kcal, ' kcal') }}
            </span>
          </div>
        </RouterLink>

        <button
          class="btn btn--ghost row-item__del"
          type="button"
          :disabled="deletingId === item.id"
          :aria-label="`删除 ${item.dish_name}`"
          @click="remove(item)"
        >
          {{ deletingId === item.id ? '删除中…' : '删除' }}
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--s-4);
  margin-bottom: var(--s-5);
}

.head__title {
  font-size: var(--fs-2xl);
  margin-bottom: var(--s-1);
}

.list {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.row-item {
  display: flex;
  align-items: center;
  gap: var(--s-4);
  padding: var(--s-4);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  box-shadow: var(--sh-1);
}

.row-item__link {
  display: flex;
  align-items: center;
  gap: var(--s-4);
  flex: 1;
  min-width: 0;
  /* The link is the tap target, so it needs the full min height on mobile. */
  min-height: var(--tap-min);
  color: inherit;
  text-decoration: none;
  border-radius: var(--r-sm);
}

.row-item__link:hover .row-item__dish {
  color: var(--c-primary);
}

.row-item__main {
  min-width: 0;
  flex: 1;
}

.row-item__dish {
  font-weight: 600;
  font-size: var(--fs-md);
  overflow-wrap: anywhere;
}

.row-item__stats {
  display: flex;
  align-items: center;
  gap: var(--s-3);
}

.row-item__kcal {
  color: var(--c-text-muted);
  font-size: var(--fs-sm);
  min-width: 5.5rem;
  text-align: right;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--s-3);
  text-align: left;
}

.notice {
  background: var(--c-surface-2);
}

@media (max-width: 620px) {
  .head {
    align-items: flex-start;
    flex-direction: column;
  }

  .row-item {
    flex-wrap: wrap;
    gap: var(--s-3);
  }

  .row-item__main {
    flex-basis: 100%;
  }

  .row-item__kcal {
    min-width: 0;
  }

  .row-item__del {
    margin-left: auto;
  }
}
</style>
