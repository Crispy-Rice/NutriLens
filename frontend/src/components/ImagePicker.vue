<script setup lang="ts">
import { computed, ref } from 'vue'
import type { SelectedImage } from '@/composables/useImageSelection'
import { formatBytes } from '@/utils/format'

const props = defineProps<{
  images: SelectedImage[]
  maxImages: number
  maxMb: number
  maxTotalMb: number
  summary: {
    count: number
    bytes: number
    originalBytes: number
    compressed: boolean
    savedPercent: number
  } | null
  preparing?: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'add', files: File[]): void
  (e: 'remove', id: string): void
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const cameraInput = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)
const dragDepth = ref(0)

const busy = computed(() => props.disabled || props.preparing)
const hasImages = computed(() => props.images.length > 0)
const room = computed(() => Math.max(0, props.maxImages - props.images.length))

function pick(): void {
  if (busy.value) return
  fileInput.value?.click()
}

function shoot(): void {
  if (busy.value) return
  cameraInput.value?.click()
}

function onChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  if (files.length) emit('add', files)
  // Reset so picking the same file twice still fires a change event.
  input.value = ''
}

function onDragEnter(): void {
  if (busy.value) return
  dragDepth.value += 1
  isDragging.value = true
}

function onDragLeave(): void {
  // dragleave also fires when moving over child elements, so count depth.
  dragDepth.value = Math.max(0, dragDepth.value - 1)
  if (dragDepth.value === 0) isDragging.value = false
}

function onDrop(event: DragEvent): void {
  dragDepth.value = 0
  isDragging.value = false
  if (busy.value) return
  const files = Array.from(event.dataTransfer?.files ?? [])
  if (files.length) emit('add', files)
}
</script>

<template>
  <div class="picker" :class="{ 'picker--dragging': isDragging }">
    <!-- ---------- empty state: a large target ---------- -->
    <button
      v-if="!hasImages"
      type="button"
      class="dz"
      :class="{ 'dz--active': isDragging, 'dz--busy': preparing }"
      :disabled="busy"
      @click="pick"
      @dragenter.prevent="onDragEnter"
      @dragover.prevent
      @dragleave.prevent="onDragLeave"
      @drop.prevent="onDrop"
    >
      <span class="dz__icon" aria-hidden="true">
        <svg viewBox="0 0 48 48" width="44" height="44" fill="none">
          <rect x="5" y="9" width="38" height="30" rx="5" stroke="currentColor" stroke-width="2.2" />
          <circle cx="17" cy="20" r="3.4" stroke="currentColor" stroke-width="2.2" />
          <path d="M8 34l10.5-10.5a3 3 0 0 1 4.3 0L36 36" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" />
          <path d="M30 31l4-4a3 3 0 0 1 4.3 0L41 31" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" />
        </svg>
      </span>
      <template v-if="preparing">
        <span class="dz__title">正在处理图片…</span>
        <span class="dz__hint">正在压缩与校验，请稍候</span>
      </template>
      <template v-else>
        <span class="dz__title">点击选择照片，或把图片拖到这里</span>
        <span class="dz__hint">
          支持 JPG / PNG / WebP，最多 {{ maxImages }} 张，单张不超过 {{ maxMb }} MB<br />
          可以传同一道菜的多个角度，也可以传一餐里的多道菜
        </span>
      </template>
    </button>

    <!-- ---------- filled state: thumbnails + add tile ---------- -->
    <div
      v-else
      class="strip"
      @dragenter.prevent="onDragEnter"
      @dragover.prevent
      @dragleave.prevent="onDragLeave"
      @drop.prevent="onDrop"
    >
      <ul class="thumbs">
        <li v-for="image in images" :key="image.id" class="thumb">
          <img :src="image.previewUrl" alt="已选择的食物照片" class="thumb__img" />
          <button
            class="thumb__remove"
            type="button"
            :disabled="busy"
            :aria-label="`移除这张照片`"
            @click="emit('remove', image.id)"
          >
            ×
          </button>
          <span class="thumb__dims mono">
            {{ image.compressed.width }}×{{ image.compressed.height }}
          </span>
        </li>

        <li v-if="room > 0" class="thumb thumb--add">
          <button
            type="button"
            class="add-tile"
            :disabled="busy"
            @click="pick"
          >
            <span aria-hidden="true">＋</span>
            <span class="add-tile__label">再加 {{ room }} 张</span>
          </button>
        </li>
      </ul>

      <p v-if="summary" class="strip__meta subtle mono">
        共 {{ summary.count }} 张 · {{ formatBytes(summary.bytes) }}
        <template v-if="summary.compressed">
          （原图 {{ formatBytes(summary.originalBytes) }}，已压缩 {{ summary.savedPercent }}%）
        </template>
      </p>
    </div>

    <div class="actions">
      <button v-if="hasImages" class="btn btn--ghost" type="button" :disabled="busy" @click="pick">
        选择图片
      </button>
      <button class="btn btn--ghost" type="button" :disabled="busy" @click="shoot">
        <span aria-hidden="true">📷</span>
        用手机拍摄
      </button>
      <p class="note subtle">
        图片仅用于本次分析，服务端处理完即删除，不长期保存。
      </p>
    </div>

    <input
      ref="fileInput"
      class="visually-hidden"
      type="file"
      multiple
      accept="image/jpeg,image/png,image/webp"
      @change="onChange"
    />
    <!-- capture="environment" opens the rear camera directly on mobile; on
         desktop this input behaves like a normal file picker. -->
    <input
      ref="cameraInput"
      class="visually-hidden"
      type="file"
      accept="image/*"
      capture="environment"
      @change="onChange"
    />
  </div>
</template>

<style scoped>
.picker {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

/* ---------- empty state ---------- */

.dz {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  width: 100%;
  min-height: 220px;
  padding: var(--s-6) var(--s-5);
  text-align: center;
  cursor: pointer;
  background: var(--c-surface);
  border: 2px dashed var(--c-border-strong);
  border-radius: var(--r-lg);
  color: var(--c-text);
  transition: border-color var(--dur) var(--ease), background var(--dur) var(--ease),
    transform var(--dur-fast) var(--ease);
}

.dz:hover:not(:disabled) {
  border-color: var(--c-primary);
  background: var(--c-primary-soft);
}

.dz:active:not(:disabled) {
  transform: scale(0.995);
}

.dz--active {
  border-color: var(--c-primary);
  background: var(--c-primary-soft);
}

.dz--busy {
  cursor: progress;
}

.dz__icon {
  color: var(--c-primary);
  margin-bottom: var(--s-1);
}

.dz__title {
  font-size: var(--fs-md);
  font-weight: 600;
}

.dz__hint {
  font-size: var(--fs-sm);
  color: var(--c-text-subtle);
  max-width: 44ch;
  line-height: 1.6;
}

/* ---------- filled state ---------- */

.strip {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  padding: var(--s-3);
  border: 2px dashed transparent;
  border-radius: var(--r-md);
  transition: border-color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.picker--dragging .strip {
  border-color: var(--c-primary);
  background: var(--c-primary-soft);
}

.thumbs {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: var(--s-2);
}

.thumb {
  position: relative;
  aspect-ratio: 4 / 3;
  border-radius: var(--r-sm);
  overflow: hidden;
  background: var(--c-surface-3);
}

.thumb__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb__remove {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border: none;
  border-radius: var(--r-full);
  background: rgba(20, 26, 21, 0.62);
  color: #fff;
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
}

.thumb__remove:hover:not(:disabled) {
  background: rgba(20, 26, 21, 0.85);
}

.thumb__dims {
  position: absolute;
  left: 4px;
  bottom: 4px;
  padding: 1px 5px;
  border-radius: var(--r-xs);
  background: rgba(20, 26, 21, 0.55);
  color: #fff;
  font-size: 0.625rem;
}

.thumb--add {
  background: none;
}

.add-tile {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  cursor: pointer;
  background: var(--c-surface-2);
  border: 1.5px dashed var(--c-border-strong);
  border-radius: var(--r-sm);
  color: var(--c-text-muted);
  font-size: 1.3rem;
}

.add-tile:hover:not(:disabled) {
  border-color: var(--c-primary);
  color: var(--c-primary);
  background: var(--c-primary-soft);
}

.add-tile__label {
  font-size: var(--fs-xs);
  font-weight: 600;
}

.strip__meta {
  padding-left: 2px;
}

/* ---------- shared ---------- */

.actions {
  display: flex;
  align-items: center;
  gap: var(--s-4);
  flex-wrap: wrap;
}

.note {
  flex: 1;
  min-width: 15rem;
}

@media (max-width: 560px) {
  .dz {
    min-height: 180px;
    padding: var(--s-5) var(--s-4);
  }

  .thumbs {
    grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
  }
}
</style>
