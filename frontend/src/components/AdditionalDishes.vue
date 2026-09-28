<script setup lang="ts">
import ConfidenceBadge from '@/components/ConfidenceBadge.vue'
import NutritionTable from '@/components/NutritionTable.vue'
import MarkdownBlock from '@/components/MarkdownBlock.vue'
import { useAppStore } from '@/stores/app'
import type { DishAnalysis } from '@/types/api'

defineProps<{ dishes: DishAnalysis[] }>()

const app = useAppStore()
</script>

<template>
  <section v-if="dishes.length > 0" class="also">
    <h3 class="also__heading">
      同餐还识别到 {{ dishes.length }} 道
    </h3>

    <article v-for="dish in dishes" :key="dish.dish_name" class="also__dish">
      <header class="also__head">
        <h4 class="also__name">{{ dish.dish_name }}</h4>
        <p v-if="dish.dish_name_alternatives.length > 0" class="also__alts subtle">
          也可能是 {{ dish.dish_name_alternatives.join(' / ') }}
        </p>
      </header>

      <ConfidenceBadge
        :confidence="dish.confidence"
        :threshold="app.config?.low_confidence_threshold ?? 0.55"
        :reason="dish.confidence_reason"
      />

      <div v-if="dish.ingredients.length > 0" class="also__block">
        <h5 class="also__label">主要食材</h5>
        <ul class="ing">
          <li v-for="item in dish.ingredients" :key="item.name" class="ing__item">
            <span class="ing__name">{{ item.name }}</span>
            <span v-if="item.estimated_amount" class="ing__amount mono">
              {{ item.estimated_amount }}
            </span>
          </li>
        </ul>
      </div>

      <div v-if="dish.portion_estimate" class="also__block">
        <h5 class="also__label">估算份量</h5>
        <p>{{ dish.portion_estimate }}</p>
      </div>

      <div class="also__block">
        <h5 class="also__label">营养估算</h5>
        <NutritionTable :nutrition="dish.nutrition" />
      </div>

      <div v-if="dish.advice" class="also__block">
        <h5 class="also__label">饮食建议</h5>
        <MarkdownBlock :content="dish.advice" collapsed-height="12rem" />
      </div>

      <div v-if="dish.risk_notes.length > 0" class="also__block">
        <h5 class="also__label">需要注意</h5>
        <ul class="notes notes--risk">
          <li v-for="note in dish.risk_notes" :key="note">{{ note }}</li>
        </ul>
      </div>
    </article>
  </section>
</template>

<style scoped>
.also {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  padding-top: var(--s-4);
  border-top: 1px solid var(--c-border);
}

.also__heading {
  font-size: var(--fs-sm);
  font-weight: 650;
  color: var(--c-text-subtle);
  letter-spacing: 0.06em;
}

.also__dish {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  padding: var(--s-4);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface-2);
}

.also__name {
  font-size: var(--fs-lg);
  overflow-wrap: anywhere;
}

.also__alts {
  margin-top: 2px;
}

.also__label {
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
}

.notes--risk {
  color: var(--c-warn);
}
</style>
