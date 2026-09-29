<script setup lang="ts">
import type { MealOverall } from '@/types/api'

defineProps<{ overall: MealOverall }>()

/**
 * Deliberately unstyled by value.
 *
 * Every level badge looks identical regardless of whether it says 偏少 or 偏多.
 * Colouring them green/red — or even ordering them — would turn a description
 * of quantity into a grade, which is the one thing this section must not do.
 */
</script>

<template>
  <section class="overall">
    <h3 class="overall__label">这一餐的整体构成</h3>

    <p v-if="overall.summary" class="overall__summary">{{ overall.summary }}</p>

    <dl v-if="overall.aspects.length > 0" class="aspects">
      <div v-for="aspect in overall.aspects" :key="aspect.label" class="aspect">
        <dt class="aspect__label">{{ aspect.label }}</dt>
        <dd class="aspect__body">
          <span v-if="aspect.level" class="aspect__level">{{ aspect.level }}</span>
          <span class="aspect__note">{{ aspect.note }}</span>
        </dd>
      </div>
    </dl>
  </section>
</template>

<style scoped>
.overall {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.overall__label {
  font-size: var(--fs-sm);
  font-weight: 650;
  color: var(--c-text-subtle);
  letter-spacing: 0.06em;
}

.overall__summary {
  font-size: var(--fs-md);
  line-height: 1.6;
}

.aspects {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.aspect {
  display: grid;
  grid-template-columns: 5rem 1fr;
  gap: var(--s-3);
  align-items: baseline;
  padding-bottom: var(--s-2);
  border-bottom: 1px solid var(--c-border);
}

.aspect:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.aspect__label {
  color: var(--c-text-muted);
  font-size: var(--fs-sm);
  font-weight: 600;
}

.aspect__body {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  flex-wrap: wrap;
}

/* Same treatment for every value — see the comment in the script block. */
.aspect__level {
  flex: none;
  padding: 1px var(--s-2);
  border-radius: var(--r-xs);
  background: var(--c-surface-3);
  color: var(--c-text-muted);
  font-size: var(--fs-xs);
  font-weight: 600;
}

.aspect__note {
  color: var(--c-text-muted);
  font-size: var(--fs-sm);
  overflow-wrap: anywhere;
}

@media (max-width: 560px) {
  .aspect {
    grid-template-columns: 1fr;
    gap: var(--s-1);
  }
}
</style>
