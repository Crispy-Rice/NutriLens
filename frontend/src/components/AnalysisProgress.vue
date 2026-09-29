<script setup lang="ts">
import { computed } from 'vue'
import AnalysisSections, { type AnalysisDisplay } from '@/components/AnalysisSections.vue'

/**
 * The in-progress state of an analysis.
 *
 * Deliberately shaped like the finished result card: same section order, same
 * spacing, placeholders where content hasn't arrived. The advice grows into the
 * slot it will finally occupy, so when the real result replaces this nothing
 * moves — the earlier design showed a standalone advice panel at the top, and
 * the whole card visibly jumped when the result landed.
 */
const props = defineProps<{
  /** Available early: the model writes the dish name before anything else. */
  dishName: string
  advice: string
  statusMessage: string
}>()

const emit = defineEmits<{ (e: 'cancel'): void }>()

const display = computed<AnalysisDisplay>(() => ({
  overall: null,
  ingredients: [],
  portionEstimate: null,
  nutrition: null,
  advice: props.advice,
  riskNotes: [],
  uncertaintyNotes: [],
  additionalDishes: [],
}))
</script>

<template>
  <article class="progress card">
    <header class="progress__head">
      <h2 class="progress__dish" :class="{ 'progress__dish--pending': !props.dishName }">
        {{ props.dishName || '正在识别…' }}
      </h2>
      <p class="progress__status subtle" role="status">
        {{ props.statusMessage || '正在分析…' }}
      </p>
    </header>

    <!-- The confidence block lands here; hold its space. -->
    <div class="conf-hold">
      <span class="conf-hold__bar"></span>
      <span class="conf-hold__bar conf-hold__bar--short"></span>
    </div>

    <AnalysisSections :display="display" pending streaming-advice />

    <footer class="progress__foot">
      <button class="btn" type="button" @click="emit('cancel')">取消分析</button>
    </footer>
  </article>
</template>

<style scoped>
.progress {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.progress__head {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.progress__dish {
  font-size: var(--fs-2xl);
  letter-spacing: -0.01em;
  overflow-wrap: anywhere;
}

.progress__dish--pending {
  color: var(--c-text-subtle);
  font-weight: 550;
}

.progress__status {
  font-size: var(--fs-sm);
}

.conf-hold {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  padding: var(--s-3);
  border-radius: var(--r-sm);
  background: var(--c-surface-2);
  border: 1px solid var(--c-border);
}

.conf-hold__bar {
  display: block;
  height: 0.75rem;
  border-radius: var(--r-xs);
  background: var(--c-surface-3);
  animation: conf-pulse 1.6s ease-in-out infinite;
}

.conf-hold__bar--short {
  width: 58%;
}

@keyframes conf-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.55;
  }
}

.progress__foot {
  display: flex;
  justify-content: flex-end;
  padding-top: var(--s-2);
  border-top: 1px solid var(--c-border);
}

@media (max-width: 560px) {
  .progress__dish {
    font-size: var(--fs-xl);
  }

  .progress__foot .btn {
    width: 100%;
  }
}
</style>
