<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AnalysisResult, ProcessedImage } from '@/types/api'
import ConfidenceBadge from '@/components/ConfidenceBadge.vue'
import NutritionTable from '@/components/NutritionTable.vue'
import MarkdownBlock from '@/components/MarkdownBlock.vue'
import AdditionalDishes from '@/components/AdditionalDishes.vue'
import { useAppStore } from '@/stores/app'
import { useResultExport } from '@/composables/useResultExport'
import { formatDateTime } from '@/utils/format'

const props = defineProps<{ result: AnalysisResult }>()
const emit = defineEmits<{ (e: 'restart'): void }>()

const app = useAppStore()
const cardRef = ref<HTMLElement | null>(null)

const { savingPng, notice, savePng, saveJson, saveText, copyText } = useResultExport(
  () => props.result,
  cardRef,
)

const confidenceThreshold = computed(() => app.config?.low_confidence_threshold ?? 0.55)

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
    <article ref="cardRef" class="result card">
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

      <section v-if="props.result.ingredients.length > 0" class="result__block">
        <h3 class="result__label">主要食材</h3>
        <ul class="ing">
          <li v-for="item in props.result.ingredients" :key="item.name" class="ing__item">
            <span class="ing__name">{{ item.name }}</span>
            <span v-if="item.estimated_amount" class="ing__amount mono">
              {{ item.estimated_amount }}
            </span>
            <span v-if="item.note" class="ing__note subtle">{{ item.note }}</span>
          </li>
        </ul>
      </section>

      <section v-if="props.result.portion_estimate" class="result__block">
        <h3 class="result__label">估算份量</h3>
        <p>{{ props.result.portion_estimate }}</p>
      </section>

      <section class="result__block">
        <h3 class="result__label">营养估算</h3>
        <NutritionTable :nutrition="props.result.nutrition" />
      </section>

      <section v-if="props.result.advice" class="result__block">
        <h3 class="result__label">饮食建议</h3>
        <MarkdownBlock :content="props.result.advice" collapsed-height="18rem" />
      </section>

      <section v-if="props.result.risk_notes.length > 0" class="result__block">
        <h3 class="result__label">需要注意</h3>
        <ul class="notes notes--risk">
          <li v-for="note in props.result.risk_notes" :key="note">{{ note }}</li>
        </ul>
      </section>

      <section v-if="props.result.uncertainty_notes.length > 0" class="result__block">
        <h3 class="result__label">本次不确定的地方</h3>
        <ul class="notes">
          <li v-for="note in props.result.uncertainty_notes" :key="note">{{ note }}</li>
        </ul>
      </section>

      <AdditionalDishes :dishes="props.result.additional_dishes" />

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
    <div class="toolbar">
      <div class="toolbar__group">
        <button class="btn btn--ghost" type="button" :disabled="savingPng" @click="savePng">
          {{ savingPng ? '正在生成…' : '保存为图片' }}
        </button>
        <button class="btn btn--ghost" type="button" @click="saveJson">保存 JSON</button>
        <button class="btn btn--ghost" type="button" @click="saveText">保存文本</button>
        <button class="btn btn--ghost" type="button" @click="copyText">复制</button>
      </div>

      <button class="btn btn--primary" type="button" @click="emit('restart')">
        再识别一张
      </button>
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

.result__block {
  padding-top: var(--s-4);
  border-top: 1px solid var(--c-border);
}

.result__label {
  font-size: var(--fs-sm);
  font-weight: 650;
  color: var(--c-text-subtle);
  letter-spacing: 0.06em;
  margin-bottom: var(--s-3);
}

.ing {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.ing__item {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  flex-wrap: wrap;
}

.ing__name {
  font-weight: 550;
}

.ing__amount {
  font-size: var(--fs-sm);
  color: var(--c-text-muted);
}

.ing__note {
  flex-basis: 100%;
}

.notes {
  padding-left: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  color: var(--c-text-muted);
}

.notes--risk {
  color: var(--c-warn);
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
    flex-direction: column-reverse;
    align-items: stretch;
  }

  .toolbar__group {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }

  .result__dish {
    font-size: var(--fs-xl);
  }
}
</style>
