<script setup lang="ts">
import { ref } from 'vue'
import type { AnalysisResult } from '@/types/api'
import ConfidenceBadge from '@/components/ConfidenceBadge.vue'
import NutritionTable from '@/components/NutritionTable.vue'
import MarkdownBlock from '@/components/MarkdownBlock.vue'
import AdditionalDishes from '@/components/AdditionalDishes.vue'
import { useAppStore } from '@/stores/app'
import { useResultExport } from '@/composables/useResultExport'

const props = defineProps<{ result: AnalysisResult }>()

const app = useAppStore()
const cardRef = ref<HTMLElement | null>(null)
const expanded = ref(false)

const { savingPng, notice, savePng, saveJson, saveText, copyText } = useResultExport(
  () => props.result,
  cardRef,
)
</script>

<template>
  <div class="panel">
    <article ref="cardRef" class="panel__card">
      <header class="panel__head">
        <h3 class="panel__dish">{{ props.result.dish_name }}</h3>
        <span class="panel__meta subtle">
          {{ props.result.mode === 'detailed' ? '详细分析' : '快速识别' }}
          <template v-if="props.result.images.length > 1">
            · {{ props.result.images.length }} 张照片
          </template>
        </span>
      </header>

      <p v-if="props.result.profile_used" class="badge badge--primary panel__profile">
        已参考你的饮食画像
      </p>

      <ConfidenceBadge
        :confidence="props.result.confidence"
        :threshold="app.config?.low_confidence_threshold ?? 0.55"
        :reason="props.result.confidence_reason"
      />

      <p v-if="props.result.degraded" class="panel__degraded">
        模型本次没有返回标准结构，以下内容已按纯文本兜底展示。
      </p>

      <div class="panel__block">
        <h4 class="panel__label">营养估算</h4>
        <NutritionTable :nutrition="props.result.nutrition" />
      </div>

      <div v-if="props.result.advice" class="panel__block">
        <h4 class="panel__label">饮食建议</h4>
        <!-- Clamped here rather than inside MarkdownBlock, so this panel's own
             "expand details" control governs it. -->
        <div class="panel__advice" :class="{ 'panel__advice--clamped': !expanded }">
          <MarkdownBlock :content="props.result.advice" :collapsible="false" />
        </div>
      </div>

      <!-- Food safety information is never hidden behind the expander. -->
      <div v-if="props.result.risk_notes.length > 0" class="panel__block">
        <h4 class="panel__label">需要注意</h4>
        <ul class="notes notes--risk">
          <li v-for="note in props.result.risk_notes" :key="note">{{ note }}</li>
        </ul>
      </div>

      <template v-if="expanded">
        <div v-if="props.result.ingredients.length > 0" class="panel__block">
          <h4 class="panel__label">主要食材</h4>
          <ul class="ing">
            <li v-for="item in props.result.ingredients" :key="item.name" class="ing__item">
              <span class="ing__name">{{ item.name }}</span>
              <span v-if="item.estimated_amount" class="ing__amount mono">
                {{ item.estimated_amount }}
              </span>
            </li>
          </ul>
        </div>

        <div v-if="props.result.portion_estimate" class="panel__block">
          <h4 class="panel__label">估算份量</h4>
          <p>{{ props.result.portion_estimate }}</p>
        </div>

        <div v-if="props.result.uncertainty_notes.length > 0" class="panel__block">
          <h4 class="panel__label">本次不确定的地方</h4>
          <ul class="notes">
            <li v-for="note in props.result.uncertainty_notes" :key="note">{{ note }}</li>
          </ul>
        </div>

        <AdditionalDishes :dishes="props.result.additional_dishes" />

        <p class="panel__disclaimer">{{ props.result.disclaimer }}</p>
      </template>
    </article>

    <div class="panel__bar">
      <button class="panel__toggle" type="button" :aria-expanded="expanded" @click="expanded = !expanded">
        {{ expanded ? '收起详情' : '展开食材与不确定项' }}
      </button>

      <div class="panel__tools">
        <button class="link-btn" type="button" :disabled="savingPng" @click="savePng">
          {{ savingPng ? '生成中…' : '存为图片' }}
        </button>
        <button class="link-btn" type="button" @click="saveJson">JSON</button>
        <button class="link-btn" type="button" @click="saveText">文本</button>
        <button class="link-btn" type="button" @click="copyText">复制</button>
      </div>
    </div>

    <p v-if="notice" class="panel__toast" role="status">{{ notice }}</p>
  </div>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.panel__card {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  padding: var(--s-4);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  box-shadow: var(--sh-1);
}

.panel__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-3);
  flex-wrap: wrap;
}

.panel__dish {
  font-size: var(--fs-lg);
  overflow-wrap: anywhere;
}

.panel__profile {
  align-self: flex-start;
}

.panel__degraded {
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-xs);
  background: var(--c-warn-soft);
  color: var(--c-warn);
  font-size: var(--fs-sm);
}

.panel__label {
  font-size: var(--fs-xs);
  font-weight: 650;
  color: var(--c-text-subtle);
  letter-spacing: 0.06em;
  margin-bottom: var(--s-2);
}

.ing {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
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

.panel__advice {
  position: relative;
}

.panel__advice--clamped {
  max-height: 10rem;
  overflow: hidden;
}

.panel__advice--clamped::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 2.5rem;
  background: linear-gradient(to bottom, transparent, var(--c-surface));
  pointer-events: none;
}

.panel__disclaimer {
  font-size: var(--fs-xs);
  color: var(--c-text-subtle);
  line-height: 1.55;
}

.panel__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  flex-wrap: wrap;
}

.panel__toggle,
.link-btn {
  background: none;
  border: none;
  padding: 2px 0;
  color: var(--c-primary);
  font-size: var(--fs-sm);
  font-weight: 600;
  cursor: pointer;
}

.panel__toggle:hover,
.link-btn:hover {
  text-decoration: underline;
}

.link-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.panel__tools {
  display: flex;
  gap: var(--s-3);
}

.panel__toast {
  align-self: flex-start;
  padding: var(--s-1) var(--s-3);
  border-radius: var(--r-full);
  background: var(--c-text);
  color: var(--c-bg);
  font-size: var(--fs-xs);
}
</style>
