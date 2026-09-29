<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import ChatMessage from '@/components/ChatMessage.vue'
import ImagePicker from '@/components/ImagePicker.vue'
import MarkdownBlock from '@/components/MarkdownBlock.vue'
import { useConfirm } from '@/composables/useConfirm'
import { useAppStore } from '@/stores/app'
import { useConversationStore } from '@/stores/conversation'
import type { ConversationSummary } from '@/types/api'
import { formatDateTime } from '@/utils/format'

const app = useAppStore()
const conv = useConversationStore()
const { confirm } = useConfirm()

const attachOpen = ref(false)
const listOpen = ref(false)
const threadRef = ref<HTMLElement | null>(null)

const maxMb = computed(() => app.config?.max_upload_mb ?? 10)
const maxTotalMb = computed(() => app.config?.max_total_upload_mb ?? 20)

function scrollToBottom(): void {
  requestAnimationFrame(() => {
    const el = threadRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function startNew(): Promise<void> {
  conv.reset()
  attachOpen.value = false
  listOpen.value = false
  await conv.startNew()
}

async function send(): Promise<void> {
  const hadImages = conv.images.length > 0
  await conv.sendTurn()
  if (hadImages) attachOpen.value = false
  scrollToBottom()
}

async function openConversation(id: string): Promise<void> {
  listOpen.value = false
  attachOpen.value = false
  await conv.open(id)
  scrollToBottom()
}

async function removeConversation(item: ConversationSummary): Promise<void> {
  const confirmed = await confirm({
    title: '删除这段对话？',
    subject: item.title,
    message: `这段对话的 ${item.turn_count} 条消息会一并永久移除，无法撤销。`,
    details: ['原始照片在每轮分析结束后就已删除，不涉及图片。'],
    confirmLabel: '删除',
  })
  if (!confirmed) return
  await conv.remove(item.id)
}

onMounted(async () => {
  await conv.loadList()
  if (conv.active) scrollToBottom()
})
</script>

<template>
  <div class="page chat">
    <header class="head">
      <div class="head__text">
        <h1 class="head__title">对话</h1>
        <p class="subtle">
          上传照片开始一段对话，之后可以就这一餐继续追问。
          追问时也可以再附新照片。
        </p>
      </div>

      <div class="head__actions">
        <button class="btn btn--ghost" type="button" @click="listOpen = !listOpen">
          历史对话<template v-if="conv.total > 0">（{{ conv.total }}）</template>
        </button>
        <button class="btn btn--primary" type="button" @click="startNew">新对话</button>
      </div>
    </header>

    <!-- ---------- past conversations ---------- -->
    <section v-if="listOpen" class="card list">
      <p v-if="conv.loadingList" class="muted">正在读取…</p>
      <p v-else-if="conv.listError" class="alert alert--danger" role="alert">
        {{ conv.listError.message }}
      </p>
      <p v-else-if="conv.list.length === 0" class="muted">还没有对话记录。</p>
      <ul v-else class="list__items">
        <li v-for="item in conv.list" :key="item.id" class="list__item">
          <button class="list__open" type="button" @click="openConversation(item.id)">
            <span class="list__title">{{ item.title }}</span>
            <span class="subtle mono">
              {{ item.turn_count }} 条 · {{ formatDateTime(item.updated_at) }}
            </span>
          </button>
          <button
            class="list__del"
            type="button"
            :aria-label="`删除 ${item.title}`"
            @click="removeConversation(item)"
          >
            删除
          </button>
        </li>
      </ul>
    </section>

    <!-- ---------- the thread ---------- -->
    <section v-if="conv.active" ref="threadRef" class="thread">
      <p v-if="!conv.hasMessages && !conv.isResponding" class="thread__hint muted">
        先上传一张照片开始吧。识别结果会作为这段对话的基础。
      </p>

      <ChatMessage
        v-for="message in conv.active.messages"
        :key="message.id"
        :message="message"
      />

      <!-- live reply while the model is still writing -->
      <article v-if="conv.isResponding" class="msg msg--assistant">
        <span class="msg__avatar" aria-hidden="true">鉴</span>
        <div class="msg__body">
          <p class="thread__status subtle" role="status">
            <template v-if="conv.streamedDishName">
              正在识别：{{ conv.streamedDishName }}
            </template>
            <template v-else>{{ conv.statusMessage || '正在处理…' }}</template>
          </p>
          <div v-if="conv.streamedText" class="msg__prose">
            <MarkdownBlock :content="conv.streamedText" streaming :collapsible="false" />
          </div>
        </div>
      </article>
    </section>

    <section v-else class="card empty">
      <h2 class="card__title">开始一段新对话</h2>
      <p class="muted">
        上传或拍摄一张食物照片，识别完成后可以继续追问——
        比如「怎么做能更清淡」「适合搭配什么主食」。
      </p>
      <button class="btn btn--primary" type="button" @click="startNew">新对话</button>
    </section>

    <!-- ---------- errors ---------- -->
    <section v-if="conv.turnError" class="card alert-card" role="alert">
      <h2 class="card__title">这一轮没有完成</h2>
      <p>{{ conv.turnError.message }}</p>
      <p v-if="conv.turnError.hint" class="subtle">{{ conv.turnError.hint }}</p>
      <p class="subtle">你输入的内容已保留，可以直接重试。</p>
    </section>

    <!-- ---------- composer ---------- -->
    <section v-if="conv.active" class="composer card">
      <!-- The single most important thing to be honest about here: a follow-up
           cannot re-read the original photo. Saying so prevents the model's
           answer being mistaken for a fresh look. -->
      <p v-if="conv.hasDiscardedPhotos" class="notice-line subtle">
        原图在上传后即已删除。后续追问只能依据已提取的结果回答；
        如果需要模型重新看图，请再附一张照片。
      </p>

      <button
        class="attach-toggle"
        type="button"
        :aria-expanded="attachOpen"
        @click="attachOpen = !attachOpen"
      >
        {{ attachOpen ? '收起照片' : '附照片（可选）' }}
      </button>

      <div v-if="attachOpen" class="composer__picker">
        <ImagePicker
          :images="conv.images"
          :max-images="conv.maxImages"
          :max-mb="maxMb"
          :max-total-mb="maxTotalMb"
          :summary="conv.sizeSummary"
          :preparing="conv.imagePreparing"
          :disabled="conv.isResponding"
          @add="conv.addImages"
          @remove="conv.removeImage"
        />
      </div>

      <p v-if="conv.imagePrepareError" class="alert alert--danger" role="alert">
        {{ conv.imagePrepareError }}
      </p>

      <div class="composer__row">
        <label class="visually-hidden" for="chat-input">输入你的问题</label>
        <textarea
          id="chat-input"
          v-model="conv.draft"
          class="textarea composer__input"
          rows="2"
          maxlength="1000"
          :disabled="conv.isResponding"
          placeholder="就这一餐继续追问，例如：如果想少油一点，可以怎么调整？"
          @keydown.enter.exact.prevent="send"
        ></textarea>

        <div class="composer__buttons">
          <button
            v-if="conv.isResponding"
            class="btn"
            type="button"
            @click="conv.cancel()"
          >
            停止
          </button>
          <button
            v-else
            class="btn btn--primary"
            type="button"
            :disabled="!conv.canSend"
            @click="send"
          >
            发送
          </button>
        </div>
      </div>

      <p class="subtle composer__tip">按 Enter 发送，Shift + Enter 换行。</p>
    </section>
  </div>
</template>

<style scoped>
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--s-4);
  flex-wrap: wrap;
  margin-bottom: var(--s-4);
}

.head__title {
  font-size: var(--fs-2xl);
  margin-bottom: var(--s-2);
}

.head__text {
  max-width: 52ch;
}

.head__actions {
  display: flex;
  gap: var(--s-2);
  flex-wrap: wrap;
}

.page > * + * {
  margin-top: var(--s-4);
}

/* ---------- list ---------- */

.list__items {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}

.list__item {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  border-bottom: 1px solid var(--c-border);
}

.list__item:last-child {
  border-bottom: none;
}

.list__open {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: var(--s-3) var(--s-2);
  background: none;
  border: none;
  text-align: left;
  cursor: pointer;
  border-radius: var(--r-sm);
}

.list__open:hover {
  background: var(--c-surface-2);
}

.list__title {
  font-weight: 600;
  overflow-wrap: anywhere;
}

.list__del {
  background: none;
  border: none;
  padding: var(--s-2);
  color: var(--c-text-subtle);
  font-size: var(--fs-sm);
  cursor: pointer;
}

.list__del:hover {
  color: var(--c-danger);
}

/* ---------- thread ---------- */

.thread {
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
  padding: var(--s-1);
}

.thread__hint,
.thread__status {
  font-size: var(--fs-sm);
}

/* ---------- composer ---------- */

.composer {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

/* Wide screens get the app-like arrangement: a fixed-height thread that scrolls
   internally, with the composer pinned below it. Narrow screens scroll the page
   normally — a tall sticky composer would swallow a phone screen. */
@media (min-width: 721px) {
  .thread {
    max-height: 60vh;
    overflow-y: auto;
    scroll-behavior: smooth;
  }

  .composer {
    position: sticky;
    bottom: var(--s-4);
  }
}

.notice-line {
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-sm);
  background: var(--c-surface-2);
  font-size: var(--fs-sm);
}

.attach-toggle {
  align-self: flex-start;
  background: none;
  border: none;
  padding: 0;
  color: var(--c-primary);
  font-size: var(--fs-sm);
  font-weight: 600;
  cursor: pointer;
}

.attach-toggle:hover {
  text-decoration: underline;
}

.composer__row {
  display: flex;
  gap: var(--s-3);
  align-items: flex-end;
}

.composer__input {
  flex: 1;
}

.composer__buttons {
  flex: none;
}

.composer__tip {
  margin: 0;
}

.empty,
.alert-card {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  align-items: flex-start;
}

.alert-card {
  border-color: color-mix(in srgb, var(--c-danger) 35%, transparent);
}

.alert-card .card__title {
  color: var(--c-danger);
}

.alert--danger {
  padding: var(--s-3) var(--s-4);
  border-radius: var(--r-sm);
  background: var(--c-danger-soft);
  color: var(--c-danger);
  font-size: var(--fs-base);
}

@media (max-width: 560px) {
  .composer__row {
    flex-direction: column;
    align-items: stretch;
  }

  .composer__buttons {
    display: flex;
    justify-content: flex-end;
  }

  .thread {
    max-height: none;
  }
}
</style>
