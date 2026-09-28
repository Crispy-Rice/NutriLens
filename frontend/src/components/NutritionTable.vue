<script setup lang="ts">
import { computed } from 'vue'
import type { Nutrition } from '@/types/api'
import { formatNutrient } from '@/utils/format'

const props = defineProps<{ nutrition: Nutrition }>()

interface Row {
  key: keyof Nutrition
  label: string
  unit: string
  digits: number
  /** Optional nutrients are hidden entirely when the model didn't supply them. */
  optional?: boolean
}

const ROWS: Row[] = [
  { key: 'calories_kcal', label: '热量', unit: ' kcal', digits: 0 },
  { key: 'protein_g', label: '蛋白质', unit: ' g', digits: 1 },
  { key: 'fat_g', label: '脂肪', unit: ' g', digits: 1 },
  { key: 'carbs_g', label: '碳水化合物', unit: ' g', digits: 1 },
  { key: 'fiber_g', label: '膳食纤维', unit: ' g', digits: 1, optional: true },
  { key: 'sugar_g', label: '糖', unit: ' g', digits: 1, optional: true },
  { key: 'sodium_mg', label: '钠', unit: ' mg', digits: 0, optional: true },
]

const rows = computed(() =>
  ROWS.filter((row) => {
    const value = props.nutrition[row.key]
    if (row.optional) return typeof value === 'number'
    return true
  }),
)

function display(row: Row): string {
  const value = props.nutrition[row.key]
  return typeof value === 'number' ? formatNutrient(value, row.unit, row.digits) : '—'
}

function isUnknown(row: Row): boolean {
  return typeof props.nutrition[row.key] !== 'number'
}
</script>

<template>
  <div class="nut">
    <table class="nut__table">
      <caption class="visually-hidden">营养成分估算</caption>
      <tbody>
        <tr v-for="row in rows" :key="row.key" :class="{ 'is-unknown': isUnknown(row) }">
          <th scope="row">{{ row.label }}</th>
          <td class="mono">{{ display(row) }}</td>
        </tr>
      </tbody>
    </table>

    <p class="nut__basis">
      <span class="nut__basis-label">估算口径</span>
      {{ props.nutrition.basis }}
    </p>
  </div>
</template>

<style scoped>
.nut__table {
  width: 100%;
  border-collapse: collapse;
}

.nut__table th,
.nut__table td {
  padding: var(--s-2) 0;
  border-bottom: 1px solid var(--c-border);
  text-align: left;
  font-weight: 400;
}

.nut__table tr:last-child th,
.nut__table tr:last-child td {
  border-bottom: none;
}

.nut__table th {
  color: var(--c-text-muted);
  font-size: var(--fs-base);
}

.nut__table td {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}

/* An unknown value is greyed so it never reads as a measured zero. */
.is-unknown td {
  color: var(--c-text-subtle);
  font-weight: 400;
}

.nut__basis {
  margin-top: var(--s-3);
  padding-top: var(--s-3);
  border-top: 1px dashed var(--c-border);
  font-size: var(--fs-sm);
  color: var(--c-text-muted);
}

.nut__basis-label {
  display: inline-block;
  margin-right: var(--s-2);
  padding: 1px 6px;
  border-radius: var(--r-xs);
  background: var(--c-surface-3);
  font-size: var(--fs-xs);
  color: var(--c-text-subtle);
}
</style>
