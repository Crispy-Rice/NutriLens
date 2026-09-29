<script setup lang="ts">
import { computed, ref } from 'vue'
import ImagePicker from '@/components/ImagePicker.vue'
import ModeSelector from '@/components/ModeSelector.vue'
import AnalysisProgress from '@/components/AnalysisProgress.vue'
import ResultCard from '@/components/ResultCard.vue'
import ProfileSummary from '@/components/ProfileSummary.vue'
import { useAppStore } from '@/stores/app'
import { useAnalysisStore } from '@/stores/analysis'

const app = useAppStore()
const analysis = useAnalysisStore()

const noteOpen = ref(false)

const maxMb = computed(() => app.config?.max_upload_mb ?? 10)
const maxTotalMb = computed(() => app.config?.max_total_upload_mb ?? 20)
const modes = computed(() => app.modes)

async function onAdd(files: File[]): Promise<void> {
  noteOpen.value = false
  await analysis.addFiles(files)
}

function onClear(): void {
  analysis.clear()
  noteOpen.value = false
}
</script>

<template>
  <div class="page">
    <section v-if="!analysis.hasImages" class="hero">
      <p class="hero__eyebrow">食物营养识别</p>
      <h1 class="hero__title">拍一张，看清这一餐</h1>
      <p class="hero__lede">
        上传或拍摄食物照片，识别菜品与主要食材、估算份量，并给出营养估算与中立的饮食参考。
        可以一次传多张——同一道菜的多个角度，或一餐里的多道菜。结果会标注置信度，
        不确定时我们会直接告诉你。
      </p>
    </section>

    <section class="card">
      <ImagePicker
        :images="analysis.images"
        :max-images="analysis.maxImages"
        :max-mb="maxMb"
        :max-total-mb="maxTotalMb"
        :summary="analysis.sizeSummary"
        :preparing="analysis.phase === 'preparing'"
        @add="onAdd"
        @remove="analysis.removeImage"
      />

      <p v-if="analysis.prepareError" class="alert alert--danger" role="alert">
        {{ analysis.prepareError }}
      </p>
    </section>

    <!-- Surfaced before an analysis so the user can see (and set) what advice
         will be tailored to. -->
    <ProfileSummary v-if="!analysis.hasImages" />

    <template v-if="analysis.hasImages">
      <section class="card">
        <h2 class="card__title">分析模式</h2>
        <ModeSelector
          :modes="modes"
          :model-value="analysis.mode"
          :disabled="analysis.isAnalyzing"
          @update:model-value="analysis.setMode"
        />

        <div class="note">
          <button
            class="note__toggle"
            type="button"
            :aria-expanded="noteOpen"
            @click="noteOpen = !noteOpen"
          >
            {{ noteOpen ? '收起补充说明' : '添加补充说明（可选）' }}
          </button>
          <div v-if="noteOpen" class="field note__field">
            <label class="field__label" for="analysis-note">
              帮助模型更准确地判断，可留空
            </label>
            <textarea
              id="analysis-note"
              v-model="analysis.note"
              class="textarea"
              rows="2"
              maxlength="300"
              placeholder="例如：这是两人份 / 少油 / 我另外加了一勺辣椒油"
            ></textarea>
          </div>
        </div>

        <div class="actions">
          <!-- Status and cancel live in the progress card below, so this row
               only needs the trigger. It stays disabled rather than vanishing,
               so the layout does not shift when analysing starts. -->
          <button
            class="btn btn--primary btn--lg"
            type="button"
            :disabled="!analysis.canAnalyze"
            @click="analysis.analyze()"
          >
            {{ analysis.isAnalyzing ? '分析中…' : '开始分析' }}
          </button>
        </div>
      </section>

      <section v-if="analysis.error" class="card alert-card" role="alert">
        <h2 class="card__title">分析失败</h2>
        <p>{{ analysis.error.message }}</p>
        <p v-if="analysis.error.hint" class="subtle">{{ analysis.error.hint }}</p>
        <p v-if="analysis.error.requestId" class="subtle mono">
          请求编号：{{ analysis.error.requestId }}
        </p>
        <button class="btn btn--ghost" type="button" @click="analysis.analyze()">重试</button>
      </section>

      <!-- Same layout as the finished card, with placeholders — so when the
           result arrives nothing moves. -->
      <AnalysisProgress
        v-if="analysis.isAnalyzing"
        :dish-name="analysis.streamedDishName"
        :advice="analysis.streamedText"
        :status-message="analysis.statusMessage"
        @cancel="analysis.cancel()"
      />

      <ResultCard
        v-if="analysis.result"
        :result="analysis.result"
        @restart="onClear"
        @updated="analysis.setResult"
      />
    </template>
  </div>
</template>

<style scoped>
.hero {
  padding: var(--s-6) 0 var(--s-5);
}

.hero__eyebrow {
  font-size: var(--fs-xs);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--c-primary);
  font-weight: 650;
  margin-bottom: var(--s-3);
}

.hero__title {
  font-size: clamp(1.9rem, 6vw, 2.9rem);
  letter-spacing: -0.02em;
  margin-bottom: var(--s-4);
}

.hero__lede {
  max-width: 56ch;
  color: var(--c-text-muted);
  font-size: var(--fs-md);
}

.page > * + * {
  margin-top: var(--s-4);
}

.alert {
  margin-top: var(--s-4);
  padding: var(--s-3) var(--s-4);
  border-radius: var(--r-sm);
  font-size: var(--fs-base);
}

.alert--danger {
  background: var(--c-danger-soft);
  color: var(--c-danger);
}

.note {
  margin-top: var(--s-4);
  padding-top: var(--s-4);
  border-top: 1px solid var(--c-border);
}

.note__toggle {
  background: none;
  border: none;
  padding: 0;
  color: var(--c-primary);
  font-size: var(--fs-sm);
  font-weight: 600;
  cursor: pointer;
}

.note__toggle:hover {
  text-decoration: underline;
}

.note__field {
  margin-top: var(--s-3);
}

.actions {
  display: flex;
  align-items: center;
  gap: var(--s-4);
  margin-top: var(--s-5);
}

.alert-card {
  border-color: color-mix(in srgb, var(--c-danger) 35%, transparent);
}

.alert-card .card__title {
  color: var(--c-danger);
}

@media (max-width: 560px) {
  .actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
