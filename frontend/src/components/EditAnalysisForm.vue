<script setup lang="ts">
import { computed, ref } from 'vue'
import { updateAnalysis, type AnalysisEditPatch } from '@/api/client'
import { toApiError } from '@/api/client'
import type { AnalysisResult } from '@/types/api'

/**
 * Correct the parts of a recognition a person can actually judge: the dish name,
 * the ingredients and the portion.
 *
 * Nutrition is deliberately not editable. Those numbers are derived from the
 * ingredients, so letting them be edited independently would leave a card whose
 * parts contradict each other — and the note below says so plainly rather than
 * letting the user assume the figures followed their correction.
 */
const props = defineProps<{ result: AnalysisResult }>()
const emit = defineEmits<{
  (e: 'saved', result: AnalysisResult): void
  (e: 'cancel'): void
}>()

interface Row {
  name: string
  amount: string
}

const dishName = ref(props.result.dish_name)
const portion = ref(props.result.portion_estimate ?? '')
const rows = ref<Row[]>(
  props.result.ingredients.length > 0
    ? props.result.ingredients.map((i) => ({
        name: i.name,
        amount: i.estimated_amount ?? '',
      }))
    : [{ name: '', amount: '' }],
)

const saving = ref(false)
const error = ref<string | null>(null)

const canSave = computed(() => dishName.value.trim().length > 0 && !saving.value)

const isDirty = computed(() => {
  if (dishName.value.trim() !== props.result.dish_name) return true
  if ((portion.value.trim() || null) !== props.result.portion_estimate) return true
  const before = props.result.ingredients.map((i) => `${i.name}|${i.estimated_amount ?? ''}`)
  const after = rows.value
    .map((r) => `${r.name.trim()}|${r.amount.trim()}`)
    .filter((entry) => !entry.startsWith('|'))
  return JSON.stringify(before) !== JSON.stringify(after)
})

function addRow(): void {
  rows.value.push({ name: '', amount: '' })
}

function removeRow(index: number): void {
  rows.value.splice(index, 1)
  if (rows.value.length === 0) rows.value.push({ name: '', amount: '' })
}

async function save(): Promise<void> {
  if (!canSave.value) return
  saving.value = true
  error.value = null

  // Blank rows mean "removed", so they are dropped rather than rejected.
  const ingredients = rows.value
    .filter((row) => row.name.trim())
    .map((row) => ({
      name: row.name.trim(),
      estimated_amount: row.amount.trim() || null,
      note: null,
    }))

  const patch: AnalysisEditPatch = {
    dish_name: dishName.value.trim(),
    ingredients,
    portion_estimate: portion.value.trim() || null,
  }

  try {
    emit('saved', await updateAnalysis(props.result.id, patch))
  } catch (err) {
    error.value = toApiError(err).message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <article class="edit card">
    <header class="edit__head">
      <h2 class="edit__title">修正识别结果</h2>
      <p class="subtle">
        模型认错的时候，可以在这里改。修改只影响这条记录，不会重新识别。
      </p>
    </header>

    <div class="field">
      <label class="field__label" for="edit-dish">菜品名称</label>
      <input
        id="edit-dish"
        v-model="dishName"
        class="input"
        type="text"
        maxlength="60"
        placeholder="例如：番茄炒蛋"
      />
      <p v-if="!dishName.trim()" class="subtle hint hint--warn">菜品名称不能为空。</p>
    </div>

    <div class="field">
      <span class="field__label">主要食材</span>
      <ul class="rows">
        <li v-for="(row, index) in rows" :key="index" class="row">
          <input
            v-model="row.name"
            class="input row__name"
            type="text"
            maxlength="60"
            :aria-label="`第 ${index + 1} 项食材名称`"
            placeholder="食材名称"
          />
          <input
            v-model="row.amount"
            class="input row__amount"
            type="text"
            maxlength="40"
            :aria-label="`第 ${index + 1} 项用量`"
            placeholder="用量，如 约 150g"
          />
          <button
            class="row__remove"
            type="button"
            :aria-label="`移除第 ${index + 1} 项`"
            @click="removeRow(index)"
          >
            ×
          </button>
        </li>
      </ul>
      <button class="add-row" type="button" @click="addRow">＋ 添加一项</button>
    </div>

    <div class="field">
      <label class="field__label" for="edit-portion">估算份量</label>
      <input
        id="edit-portion"
        v-model="portion"
        class="input"
        type="text"
        maxlength="80"
        placeholder="例如：约 300g，约 1 人份"
      />
    </div>

    <!-- Stated rather than left implicit: the figures below are unchanged by
         anything edited above, so nobody reads them as recalculated. -->
    <p class="notice subtle">
      营养数值仍是模型按<b>原始识别</b>估算的，修改食材不会自动重算。
      它们保留在结果里，供你参考识别时的情况。
    </p>

    <p v-if="error" class="alert" role="alert">{{ error }}</p>

    <div class="edit__actions">
      <button class="btn" type="button" :disabled="saving" @click="emit('cancel')">
        取消
      </button>
      <button
        class="btn btn--primary"
        type="button"
        :disabled="!canSave || !isDirty"
        @click="save"
      >
        {{ saving ? '保存中…' : '保存修正' }}
      </button>
    </div>
  </article>
</template>

<style scoped>
.edit {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.edit__head {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.edit__title {
  font-size: var(--fs-xl);
}

.rows {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  margin-top: var(--s-1);
}

.row {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: var(--s-2);
  align-items: center;
}

.row__remove {
  width: var(--tap-min);
  height: var(--tap-min);
  display: grid;
  place-items: center;
  border: 1px solid var(--c-border-strong);
  border-radius: var(--r-sm);
  background: var(--c-surface);
  color: var(--c-text-muted);
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
}

.row__remove:hover {
  border-color: var(--c-danger);
  color: var(--c-danger);
}

.add-row {
  align-self: flex-start;
  margin-top: var(--s-2);
  background: none;
  border: none;
  padding: var(--s-2) 0;
  color: var(--c-primary);
  font-size: var(--fs-sm);
  font-weight: 600;
  cursor: pointer;
}

.add-row:hover {
  text-decoration: underline;
}

.hint {
  margin-top: var(--s-1);
}

.hint--warn {
  color: var(--c-danger);
}

.notice {
  padding: var(--s-3);
  border-radius: var(--r-sm);
  background: var(--c-surface-2);
  line-height: 1.6;
}

.alert {
  padding: var(--s-3);
  border-radius: var(--r-sm);
  background: var(--c-danger-soft);
  color: var(--c-danger);
  font-size: var(--fs-sm);
}

.edit__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--s-2);
  padding-top: var(--s-3);
  border-top: 1px solid var(--c-border);
}

@media (max-width: 560px) {
  .row {
    grid-template-columns: 1fr auto;
  }

  .row__name {
    grid-column: 1 / -1;
  }

  .edit__actions {
    flex-direction: column-reverse;
  }

  .edit__actions .btn {
    width: 100%;
  }
}
</style>
