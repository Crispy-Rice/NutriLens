<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AnalysisResult, ProcessedImage } from '@/types/api'
import ConfidenceBadge from '@/components/ConfidenceBadge.vue'
import AnalysisSections, { type AnalysisDisplay } from '@/components/AnalysisSections.vue'
import EditAnalysisForm from '@/components/EditAnalysisForm.vue'
import { useAppStore } from '@/stores/app'
import { useResultExport } from '@/composables/useResultExport'
import { formatDateTime } from '@/utils/format'

const props = defineProps<{ result: AnalysisResult }>()
const emit = defineEmits<{
  (e: 'restart'): void
  /** The stored record changed, so the owner should adopt the new value. */
  (e: 'updated', result: AnalysisResult): void
}>()

const app = useAppStore()
const cardRef = ref<HTMLElement | null>(null)
const editing = ref(false)

function onSaved(updated: AnalysisResult): void {
  editing.value = false
  emit('updated', updated)
}

const { savingPng, notice, savePng, saveJson, saveText, copyText } = useResultExport(
  () => props.result,
  cardRef,
)

const confidenceThreshold = computed(() => app.config?.low_confidence_threshold ?? 0.55)

// Feeds the shared body. The same shape is used, with nulls, while analysing —
// which is what keeps the two states laid out identically.
const display = computed<AnalysisDisplay>(() => ({
  overall: props.result.overall,
  ingredients: props.result.ingredients,
  portionEstimate: props.result.portion_estimate,
  nutrition: props.result.nutrition,
  advice: props.result.advice,
  riskNotes: props.result.risk_notes,
  uncertaintyNotes: props.result.uncertainty_notes,
  additionalDishes: props.result.additional_dishes,
}))

function describeOps(image: ProcessedImage): string {
  return image.operations.length > 0 ? image.operations.join(' · ') : '未做额外处理'
}

/**
 * Multi-image sets usually get identical treatment. Collapse to one line when
 * so, and only enumerate per image when they actually differ.
 */
const imageOps = computed(() => {
  const images = props.result.images
  if (images.length === 0) return null

  const first = describeOps(images[0])
  const allSame = images.every((image) => describeOps(image) === first)

  if (images.length === 1) return { single: true, text: first, lines: [] as string[] }
  if (allSame) {
    return { single: false, text: `共 ${images.length} 张：${first}`, lines: [] as string[] }
  }
  return {
    single: false,
    text: `共 ${images.length} 张`,
    lines: images.map((image) => `第 ${image.index + 1} 张：${describeOps(image)}`),
  }
})
</script>

<template>
  <div class="wrap">
    <EditAnalysisForm
      v-if="editing"
      :result="props.result"
      @saved="onSaved"
      @cancel="editing = false"
    />

    <article v-else ref="cardRef" class="result card">
      <header class="result__head">
        <div class="result__title">
          <h2 class="result__dish">{{ props.result.dish_name }}</h2>
          <p class="result__meta subtle">
            {{ props.result.mode === 'detailed' ? '详细分析' : '快速识别' }} ·
            {{ formatDateTime(props.result.created_at) }}
            <template v-if="props.result.images.length > 1">
              · {{ props.result.images.length }} 张照片
            </template>
          </p>
        </div>

        <!-- Makes the profile's influence visible rather than silent. -->
        <p v-if="props.result.profile_used" class="badge badge--primary result__profile">
          已参考你的饮食画像
        </p>

        <!-- Without this the corrected values would sit under an "AI estimate"
             disclaimer as if the model had produced them. -->
        <p v-if="props.result.edited" class="badge badge--accent result__profile">
          已人工修正
        </p>

        <div v-if="props.result.dish_name_alternatives.length > 0" class="result__alts">
          <span class="subtle">也可能是</span>
          <span
            v-for="alt in props.result.dish_name_alternatives"
            :key="alt"
            class="badge"
          >
            {{ alt }}
          </span>
        </div>
      </header>

      <ConfidenceBadge
        :confidence="props.result.confidence"
        :threshold="confidenceThreshold"
        :reason="props.result.confidence_reason"
      />

      <p v-if="props.result.degraded" class="result__degraded">
        模型本次没有返回标准结构，以下内容已按纯文本兜底展示，部分字段可能缺失。
      </p>

      <AnalysisSections :display="display" />

      <footer class="result__foot">
        <div v-if="imageOps" class="result__ops subtle">
          <p>图片处理：{{ imageOps.text }}</p>
          <p v-for="line in imageOps.lines" :key="line" class="result__ops-line">
            {{ line }}
          </p>
        </div>
        <p class="result__disclaimer">{{ props.result.disclaimer }}</p>
      </footer>
    </article>

    <!-- Toolbar lives outside the captured node so the exported PNG doesn't
         contain buttons. -->
    <div v-if="!editing" class="toolbar">
      <!-- Split so that on a phone the two actions people actually reach for
           can stay pinned to the bottom while the card scrolls past. -->
      <div class="toolbar__group">
        <button class="btn btn--ghost" type="button" :disabled="savingPng" @click="savePng">
          {{ savingPng ? '正在生成…' : '保存为图片' }}
        </button>
        <button class="btn btn--ghost" type="button" @click="saveJson">JSON</button>
        <button class="btn btn--ghost" type="button" @click="saveText">文本</button>
        <button class="btn btn--ghost" type="button" @click="copyText">复制</button>
      </div>

      <div class="toolbar__primary">
        <button class="btn btn--ghost" type="button" @click="editing = true">
          修正识别
        </button>
        <button class="btn btn--primary" type="button" @click="emit('restart')">
          再识别一张
        </button>
      </div>
    </div>

    <p v-if="notice" class="toast" role="status">{{ notice }}</p>
  </div>
</template>

<style scoped>
.wrap {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.result {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.result__head {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.result__dish {
  font-size: var(--fs-2xl);
  letter-spacing: -0.01em;
  overflow-wrap: anywhere;
}

.result__alts {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  flex-wrap: wrap;
}

.result__profile {
  align-self: flex-start;
}

.result__degraded {
  padding: var(--s-3);
  border-radius: var(--r-sm);
  background: var(--c-warn-soft);
  color: var(--c-warn);
  font-size: var(--fs-sm);
}

.result__foot {
  padding-top: var(--s-4);
  border-top: 1px solid var(--c-border);
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.result__ops {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.result__disclaimer {
  font-size: var(--fs-xs);
  color: var(--c-text-subtle);
  line-height: 1.55;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  flex-wrap: wrap;
}

.toolbar__group {
  display: flex;
  gap: var(--s-2);
  flex-wrap: wrap;
}

.toolbar__primary {
  display: flex;
  gap: var(--s-2);
}

.toast {
  align-self: center;
  padding: var(--s-2) var(--s-4);
  border-radius: var(--r-full);
  background: var(--c-text);
  color: var(--c-bg);
  font-size: var(--fs-sm);
}

@media (max-width: 560px) {
  .toolbar {
    flex-direction: column;
    align-items: stretch;
    gap: var(--s-2);
  }

  .toolbar__group {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }

  /* Pinned to the bottom of the viewport for as long as the card is on screen,
     with room for the home indicator beneath it. */
  .toolbar__primary {
    position: sticky;
    bottom: 0;
    z-index: 10;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--s-2);
    padding: var(--s-3) 0 calc(var(--s-3) + env(safe-area-inset-bottom, 0px));
    background: color-mix(in srgb, var(--c-bg) 94%, transparent);
    backdrop-filter: blur(8px);
    border-top: 1px solid var(--c-border);
  }

  .result__dish {
    font-size: var(--fs-xl);
  }
}
</style>
