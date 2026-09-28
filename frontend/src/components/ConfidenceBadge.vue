<script setup lang="ts">
import { computed } from 'vue'
import { confidenceBand } from '@/utils/format'

const props = defineProps<{
  confidence: number
  threshold: number
  reason?: string | null
}>()

const band = computed(() => confidenceBand(props.confidence, props.threshold))

/** Five coarse blocks. Deliberately not a percentage — see confidenceBand(). */
const filled = computed(() => {
  const c = props.confidence
  if (c >= 0.75) return 4
  if (c >= 0.55) return 3
  if (c >= 0.35) return 2
  return 1
})
</script>

<template>
  <div class="conf" :class="`conf--${band.tone}`">
    <div class="conf__head">
      <span class="conf__label">{{ band.label }}</span>
      <span class="conf__meter" :aria-label="`识别置信度：${band.label}`" role="img">
        <i v-for="n in 5" :key="n" :class="{ 'is-on': n <= filled }"></i>
      </span>
    </div>

    <p v-if="props.reason" class="conf__reason">{{ props.reason }}</p>

    <p v-if="band.needsConfirmation" class="conf__warn">
      可能识别不准，请对照照片确认菜品，或重新拍摄一张更清晰的照片。
    </p>
  </div>
</template>

<style scoped>
.conf {
  padding: var(--s-3);
  border-radius: var(--r-sm);
  background: var(--c-surface-2);
  border: 1px solid var(--c-border);
}

.conf__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
}

.conf__label {
  font-weight: 650;
  font-size: var(--fs-base);
}

.conf__meter {
  display: inline-flex;
  gap: 3px;
}

.conf__meter i {
  width: 14px;
  height: 6px;
  border-radius: var(--r-full);
  background: var(--c-border-strong);
  transition: background var(--dur) var(--ease);
}

.conf--primary {
  border-color: color-mix(in srgb, var(--c-primary) 30%, transparent);
}
.conf--primary .conf__label {
  color: var(--c-primary);
}
.conf--primary .conf__meter i.is-on {
  background: var(--c-primary);
}

.conf--accent {
  border-color: color-mix(in srgb, var(--c-accent) 35%, transparent);
}
.conf--accent .conf__label {
  color: var(--c-accent);
}
.conf--accent .conf__meter i.is-on {
  background: var(--c-accent);
}

.conf--danger {
  border-color: color-mix(in srgb, var(--c-danger) 35%, transparent);
  background: var(--c-danger-soft);
}
.conf--danger .conf__label {
  color: var(--c-danger);
}
.conf--danger .conf__meter i.is-on {
  background: var(--c-danger);
}

.conf__reason {
  margin-top: var(--s-2);
  font-size: var(--fs-sm);
  color: var(--c-text-muted);
}

.conf__warn {
  margin-top: var(--s-2);
  font-size: var(--fs-sm);
  font-weight: 550;
  color: var(--c-danger);
}
</style>
