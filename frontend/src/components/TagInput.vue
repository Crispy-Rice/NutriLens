<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string[]
    label: string
    placeholder?: string
    hint?: string
    maxItems?: number
    maxItemChars?: number
    suggestions?: string[]
  }>(),
  { maxItems: 20, maxItemChars: 30, placeholder: '', hint: '', suggestions: () => [] },
)

const emit = defineEmits<{ (e: 'update:modelValue', value: string[]): void }>()

const draft = ref('')
const inputRef = ref<HTMLInputElement | null>(null)

const atLimit = computed(() => props.modelValue.length >= props.maxItems)

const remainingSuggestions = computed(() =>
  props.suggestions.filter((s) => !props.modelValue.includes(s)).slice(0, 6),
)

function commit(raw?: string): void {
  const text = (raw ?? draft.value).trim().slice(0, props.maxItemChars)
  if (!text) return
  if (atLimit.value) return
  if (props.modelValue.includes(text)) {
    draft.value = ''
    return
  }
  emit('update:modelValue', [...props.modelValue, text])
  draft.value = ''
}

function remove(index: number): void {
  const next = [...props.modelValue]
  next.splice(index, 1)
  emit('update:modelValue', next)
}

function onKeydown(event: KeyboardEvent): void {
  // Enter and the comma keys both commit — people type lists either way.
  if (event.key === 'Enter' || event.key === ',' || event.key === '，') {
    event.preventDefault()
    commit()
    return
  }
  if (event.key === 'Backspace' && !draft.value && props.modelValue.length > 0) {
    remove(props.modelValue.length - 1)
  }
}

function onBlur(): void {
  // Don't lose a half-typed entry when the user tabs away.
  commit()
}
</script>

<template>
  <div class="tag">
    <label class="field__label" :for="`tag-${props.label}`">{{ props.label }}</label>

    <div class="tag__box" :class="{ 'tag__box--full': atLimit }">
      <span v-for="(item, index) in props.modelValue" :key="item" class="tag__chip">
        {{ item }}
        <button
          type="button"
          class="tag__x"
          :aria-label="`移除 ${item}`"
          @click="remove(index)"
        >
          ×
        </button>
      </span>

      <input
        :id="`tag-${props.label}`"
        ref="inputRef"
        v-model="draft"
        class="tag__input"
        type="text"
        :placeholder="props.modelValue.length === 0 ? props.placeholder : ''"
        :maxlength="props.maxItemChars"
        :disabled="atLimit"
        @keydown="onKeydown"
        @blur="onBlur"
      />
    </div>

    <div v-if="remainingSuggestions.length > 0 && !atLimit" class="tag__suggest">
      <span class="subtle">常用：</span>
      <button
        v-for="s in remainingSuggestions"
        :key="s"
        type="button"
        class="tag__suggest-btn"
        @click="commit(s)"
      >
        {{ s }}
      </button>
    </div>

    <p class="subtle tag__hint">
      {{ props.hint }}
      <template v-if="props.modelValue.length > 0">
        （{{ props.modelValue.length }}/{{ props.maxItems }}）
      </template>
    </p>
  </div>
</template>

<style scoped>
.tag {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.tag__box {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-1);
  min-height: var(--tap-min);
  padding: var(--s-2);
  background: var(--c-surface);
  border: 1px solid var(--c-border-strong);
  border-radius: var(--r-sm);
  transition: border-color var(--dur-fast) var(--ease);
}

.tag__box:focus-within {
  border-color: var(--c-primary);
  box-shadow: 0 0 0 3px var(--c-primary-ring);
}

.tag__box--full {
  background: var(--c-surface-2);
}

.tag__chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px var(--s-2);
  border-radius: var(--r-full);
  background: var(--c-primary-soft);
  color: var(--c-primary);
  font-size: var(--fs-sm);
  font-weight: 550;
}

.tag__x {
  border: none;
  background: none;
  color: inherit;
  font-size: 1rem;
  line-height: 1;
  padding: 0 2px;
  cursor: pointer;
  opacity: 0.7;
}

.tag__x:hover {
  opacity: 1;
}

.tag__input {
  flex: 1;
  min-width: 7rem;
  border: none;
  background: none;
  padding: var(--s-1) 0;
  outline: none;
}

.tag__suggest {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-1);
}

.tag__suggest-btn {
  border: 1px solid var(--c-border-strong);
  background: var(--c-surface);
  border-radius: var(--r-full);
  padding: 2px var(--s-2);
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
  cursor: pointer;
}

.tag__suggest-btn:hover {
  border-color: var(--c-primary);
  color: var(--c-primary);
}

.tag__hint {
  margin: 0;
}
</style>
