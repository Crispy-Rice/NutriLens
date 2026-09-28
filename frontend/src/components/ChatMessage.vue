<script setup lang="ts">
import { computed } from 'vue'
import AnalysisPanel from '@/components/AnalysisPanel.vue'
import MarkdownBlock from '@/components/MarkdownBlock.vue'
import type { ConversationMessage } from '@/types/api'

const props = defineProps<{ message: ConversationMessage }>()

const isUser = computed(() => props.message.role === 'user')

const photoSummary = computed(() => {
  const images = props.message.images
  if (images.length === 0) return ''
  const first = images[0]
  const shape = `${first.width}×${first.height}`
  return images.length === 1
    ? `1 张照片 · ${shape}`
    : `${images.length} 张照片 · ${shape} 起`
})
</script>

<template>
  <article class="msg" :class="isUser ? 'msg--user' : 'msg--assistant'">
    <span class="msg__avatar" aria-hidden="true">{{ isUser ? '我' : '鉴' }}</span>

    <div class="msg__body">
      <template v-if="isUser">
        <p v-if="props.message.text" class="msg__text">{{ props.message.text }}</p>
        <!-- The photos were deleted after their turn, so there is nothing to
             show. Saying so is more honest than an empty frame. -->
        <p v-if="photoSummary" class="msg__photos subtle">
          <span aria-hidden="true">📷</span>
          {{ photoSummary }} · 原图已删除
        </p>
      </template>

      <template v-else>
        <AnalysisPanel v-if="props.message.analysis" :result="props.message.analysis" />
        <div v-else class="msg__prose">
          <MarkdownBlock :content="props.message.text" collapsed-height="22rem" />
        </div>
      </template>
    </div>
  </article>
</template>

<style scoped>
.msg {
  display: flex;
  gap: var(--s-3);
  align-items: flex-start;
}

.msg--user {
  flex-direction: row-reverse;
}

.msg__avatar {
  flex: none;
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: var(--r-full);
  font-size: var(--fs-sm);
  font-weight: 650;
  background: var(--c-surface-3);
  color: var(--c-text-muted);
}

.msg--assistant .msg__avatar {
  background: var(--c-primary-soft);
  color: var(--c-primary);
}

.msg__body {
  min-width: 0;
  max-width: min(100%, 46rem);
}

.msg--user .msg__body {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--s-1);
}

.msg__text {
  padding: var(--s-3) var(--s-4);
  border-radius: var(--r-md);
  background: var(--c-primary-soft);
  color: var(--c-text);
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.msg__photos {
  font-size: var(--fs-xs);
}

.msg__prose {
  padding: var(--s-4);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  box-shadow: var(--sh-1);
}
</style>
