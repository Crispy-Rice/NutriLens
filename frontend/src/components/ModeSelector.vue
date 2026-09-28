<script setup lang="ts">
import type { AnalysisMode, ModeOption } from '@/types/api'

const props = defineProps<{
  modes: ModeOption[]
  modelValue: AnalysisMode
  disabled?: boolean
}>()

const emit = defineEmits<{ (e: 'update:modelValue', value: AnalysisMode): void }>()

function choose(value: AnalysisMode): void {
  if (props.disabled) return
  emit('update:modelValue', value)
}
</script>

<template>
  <fieldset class="modes" :disabled="disabled">
    <legend class="visually-hidden">选择分析模式</legend>

    <label
      v-for="option in props.modes"
      :key="option.value"
      class="mode"
      :class="{ 'mode--on': option.value === props.modelValue }"
    >
      <input
        class="visually-hidden"
        type="radio"
        name="analysis-mode"
        :value="option.value"
        :checked="option.value === props.modelValue"
        @change="choose(option.value)"
      />
      <span class="mode__dot" aria-hidden="true"></span>
      <span class="mode__body">
        <span class="mode__label">{{ option.label }}</span>
        <span class="mode__desc">{{ option.description }}</span>
      </span>
    </label>
  </fieldset>
</template>

<style scoped>
.modes {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: var(--s-3);
  border: none;
  padding: 0;
  margin: 0;
}

.mode {
  display: flex;
  align-items: flex-start;
  gap: var(--s-3);
  padding: var(--s-4);
  background: var(--c-surface);
  border: 1.5px solid var(--c-border);
  border-radius: var(--r-md);
  cursor: pointer;
  transition: border-color var(--dur-fast) var(--ease),
    background var(--dur-fast) var(--ease);
}

.mode:hover {
  border-color: var(--c-border-strong);
}

.mode--on {
  border-color: var(--c-primary);
  background: var(--c-primary-soft);
}

.mode__dot {
  flex: none;
  width: 18px;
  height: 18px;
  margin-top: 2px;
  border-radius: var(--r-full);
  border: 2px solid var(--c-border-strong);
  background: var(--c-surface);
  transition: border-color var(--dur-fast) var(--ease),
    box-shadow var(--dur-fast) var(--ease);
}

.mode--on .mode__dot {
  border-color: var(--c-primary);
  box-shadow: inset 0 0 0 4px var(--c-primary);
}

/* Focus ring on the wrapper, since the real input is visually hidden. */
.mode:has(input:focus-visible) {
  outline: 2px solid var(--c-primary);
  outline-offset: 2px;
}

.mode__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.mode__label {
  font-weight: 600;
  font-size: var(--fs-base);
}

.mode--on .mode__label {
  color: var(--c-primary);
}

.mode__desc {
  font-size: var(--fs-sm);
  color: var(--c-text-muted);
}

.modes:disabled .mode {
  cursor: not-allowed;
  opacity: 0.6;
}
</style>
