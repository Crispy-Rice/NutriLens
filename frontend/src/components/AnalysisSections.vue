<script setup lang="ts">
import type { DishAnalysis, Ingredient, MealOverall, Nutrition } from '@/types/api'
import NutritionTable from '@/components/NutritionTable.vue'
import MarkdownBlock from '@/components/MarkdownBlock.vue'
import AdditionalDishes from '@/components/AdditionalDishes.vue'
import OverallPanel from '@/components/OverallPanel.vue'

/**
 * The ordered body of an analysis.
 *
 * This exists so the progress view and the finished result card render the
 * *same* sections in the *same* order: while the model is still writing, the
 * card is already laid out with placeholders and the advice grows into the slot
 * it will finally occupy. Defining the order once is what stops the two views
 * drifting apart — which is exactly what made the old 「正在生成建议」 panel jump.
 */
export interface AnalysisDisplay {
  overall: MealOverall | null
  ingredients: Ingredient[]
  portionEstimate: string | null
  nutrition: Nutrition | null
  advice: string
  riskNotes: string[]
  uncertaintyNotes: string[]
  additionalDishes: DishAnalysis[]
}

const props = withDefaults(
  defineProps<{
    display: AnalysisDisplay
    /** Draw skeleton placeholders for sections with no content yet. */
    pending?: boolean
    /** Advice is still arriving: show a caret and no collapse control. */
    streamingAdvice?: boolean
    /** Offer the measured expand/collapse control on long advice. */
    adviceCollapsible?: boolean
  }>(),
  { pending: false, streamingAdvice: false, adviceCollapsible: true },
)

const SKELETON_WIDTHS = ['92%', '78%', '86%']
</script>

<template>
  <div class="sections">
    <!-- 1. overall -->
    <section v-if="display.overall" class="block">
      <OverallPanel :overall="display.overall" />
    </section>
    <section v-else-if="pending" class="block">
      <h3 class="label">这一餐的整体构成</h3>
      <div class="skeleton">
        <span v-for="w in SKELETON_WIDTHS" :key="w" :style="{ width: w }"></span>
      </div>
    </section>

    <!-- 2. ingredients -->
    <section v-if="display.ingredients.length > 0" class="block">
      <h3 class="label">主要食材</h3>
      <ul class="ing">
        <li v-for="item in display.ingredients" :key="item.name" class="ing__item">
          <span class="ing__name">{{ item.name }}</span>
          <span v-if="item.estimated_amount" class="ing__amount mono">
            {{ item.estimated_amount }}
          </span>
          <span v-if="item.note" class="ing__note subtle">{{ item.note }}</span>
        </li>
      </ul>
    </section>
    <section v-else-if="pending" class="block">
      <h3 class="label">主要食材</h3>
      <div class="skeleton">
        <span v-for="w in SKELETON_WIDTHS" :key="w" :style="{ width: w }"></span>
      </div>
    </section>

    <!-- 3. portion -->
    <section v-if="display.portionEstimate" class="block">
      <h3 class="label">估算份量</h3>
      <p>{{ display.portionEstimate }}</p>
    </section>
    <section v-else-if="pending" class="block">
      <h3 class="label">估算份量</h3>
      <div class="skeleton"><span style="width: 45%"></span></div>
    </section>

    <!-- 4. nutrition -->
    <section v-if="display.nutrition" class="block">
      <h3 class="label">营养估算</h3>
      <NutritionTable :nutrition="display.nutrition" />
    </section>
    <section v-else-if="pending" class="block">
      <h3 class="label">营养估算</h3>
      <div class="skeleton">
        <span v-for="w in ['70%', '62%', '66%', '58%']" :key="w" :style="{ width: w }"></span>
      </div>
    </section>

    <!-- 5. advice — the section that actually streams -->
    <section v-if="display.advice" class="block">
      <h3 class="label">饮食建议</h3>
      <MarkdownBlock
        :content="display.advice"
        :streaming="streamingAdvice"
        :collapsible="adviceCollapsible && !streamingAdvice"
      />
    </section>
    <section v-else-if="pending" class="block">
      <h3 class="label">饮食建议</h3>
      <div class="skeleton"><span style="width: 88%"></span></div>
    </section>

    <!-- 6. risk notes -->
    <section v-if="display.riskNotes.length > 0" class="block">
      <h3 class="label">需要注意</h3>
      <ul class="notes notes--risk">
        <li v-for="note in display.riskNotes" :key="note">{{ note }}</li>
      </ul>
    </section>
    <section v-else-if="pending" class="block">
      <h3 class="label">需要注意</h3>
      <div class="skeleton"><span style="width: 74%"></span></div>
    </section>

    <!-- 7. uncertainty -->
    <section v-if="display.uncertaintyNotes.length > 0" class="block">
      <h3 class="label">本次不确定的地方</h3>
      <ul class="notes">
        <li v-for="note in display.uncertaintyNotes" :key="note">{{ note }}</li>
      </ul>
    </section>
    <section v-else-if="pending" class="block">
      <h3 class="label">本次不确定的地方</h3>
      <div class="skeleton"><span style="width: 68%"></span></div>
    </section>

    <!-- 8. other dishes — unknowable until the reply lands, so no skeleton -->
    <AdditionalDishes :dishes="display.additionalDishes" />
  </div>
</template>

<style scoped>
.sections {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.block {
  padding-top: var(--s-4);
  border-top: 1px solid var(--c-border);
}

.block:first-child {
  padding-top: 0;
  border-top: none;
}

.label {
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

/* Placeholders keep the layout from collapsing, so nothing shifts when the
   real content replaces them. */
.skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.skeleton span {
  display: block;
  height: 0.75rem;
  border-radius: var(--r-xs);
  background: var(--c-surface-3);
  animation: skeleton-pulse 1.6s ease-in-out infinite;
}

@keyframes skeleton-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.55;
  }
}
</style>
