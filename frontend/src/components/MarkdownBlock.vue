<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'

const props = withDefaults(
  defineProps<{
    content: string
    /** Renders a caret and skips the collapse control while text is arriving. */
    streaming?: boolean
    /** Collapse long content behind a toggle so it can't dominate the page. */
    collapsible?: boolean
    collapsedHeight?: string
  }>(),
  { streaming: false, collapsible: true, collapsedHeight: '15rem' },
)

// Advice is model output, i.e. untrusted text, so every tag is stripped except
// this allowlist and links get hardened below.
const ALLOWED_TAGS = [
  'p', 'br', 'strong', 'em', 'del', 'code', 'pre', 'blockquote',
  'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'table', 'thead', 'tbody', 'tr', 'th', 'td', 'hr', 'a', 'span',
]

let hookInstalled = false
function ensureLinkHook(): void {
  if (hookInstalled) return
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node instanceof Element && node.tagName === 'A') {
      node.setAttribute('target', '_blank')
      node.setAttribute('rel', 'noopener noreferrer nofollow')
    }
  })
  hookInstalled = true
}

const html = computed(() => {
  if (!props.content) return ''
  ensureLinkHook()
  const raw = marked.parse(props.content, { gfm: true, breaks: true, async: false })
  return DOMPurify.sanitize(raw, { ALLOWED_TAGS, ALLOWED_ATTR: ['href'] })
})

const bodyRef = ref<HTMLElement | null>(null)
const expanded = defineModel<boolean>('expanded', { default: false })

/**
 * Decide whether to offer the toggle by measuring the rendered height rather
 * than guessing from character count — lists, headings and tables all change
 * how much space the same number of characters occupies, and a wrong guess
 * would hide the control exactly when the text overflows.
 */
const overflowing = ref(false)

const collapsedPx = computed(() => {
  const rem = /^([\d.]+)rem$/.exec(props.collapsedHeight)
  if (rem) {
    const rootSize = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16
    return parseFloat(rem[1]) * rootSize
  }
  return parseFloat(props.collapsedHeight) || 240
})

function measure(): void {
  const el = bodyRef.value
  if (!el) {
    overflowing.value = false
    return
  }
  // scrollHeight reports the full content height even while max-height clamps
  // it, so this is measurable in the collapsed state.
  overflowing.value = el.scrollHeight > collapsedPx.value + 8
}

watch(
  () => [props.content, props.collapsible, props.collapsedHeight],
  () => void nextTick(measure),
)

onMounted(() => {
  measure()
  window.addEventListener('resize', measure, { passive: true })
})

onBeforeUnmount(() => window.removeEventListener('resize', measure))

const showToggle = computed(
  () => props.collapsible && overflowing.value && !props.streaming,
)
const collapsed = computed(() => showToggle.value && !expanded.value)
</script>

<template>
  <div class="md">
    <div
      ref="bodyRef"
      class="md__body"
      :class="{ 'md__body--clamped': collapsed }"
      :style="collapsed ? { maxHeight: props.collapsedHeight } : undefined"
      v-html="html"
    ></div>

    <div v-if="collapsed" class="md__fade" aria-hidden="true"></div>

    <button
      v-if="showToggle"
      class="md__toggle"
      type="button"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      {{ expanded ? '收起' : '展开全文' }}
    </button>

    <span v-if="props.streaming" class="md__caret" aria-hidden="true"></span>
  </div>
</template>

<style scoped>
.md {
  position: relative;
}

.md__body {
  overflow-y: auto;
  overflow-wrap: anywhere;
  line-height: 1.7;
}

.md__body--clamped {
  overflow: hidden;
}

/* Markdown arrives as raw HTML, so it isn't covered by scoped styles. The
   :deep() selectors reach into it. */
.md__body :deep(h1),
.md__body :deep(h2),
.md__body :deep(h3),
.md__body :deep(h4) {
  font-size: var(--fs-md);
  margin: var(--s-4) 0 var(--s-2);
}

.md__body :deep(h1:first-child),
.md__body :deep(h2:first-child),
.md__body :deep(h3:first-child),
.md__body :deep(p:first-child) {
  margin-top: 0;
}

.md__body :deep(p) {
  margin: 0 0 var(--s-3);
}

.md__body :deep(ul),
.md__body :deep(ol) {
  margin: 0 0 var(--s-3);
  padding-left: 1.25rem;
}

.md__body :deep(li) {
  margin-bottom: var(--s-1);
}

.md__body :deep(code) {
  font-family: var(--font-mono);
  font-size: 0.875em;
  background: var(--c-surface-2);
  padding: 1px 5px;
  border-radius: var(--r-xs);
}

.md__body :deep(pre) {
  background: var(--c-surface-2);
  padding: var(--s-3);
  border-radius: var(--r-sm);
  overflow-x: auto;
  margin-bottom: var(--s-3);
}

.md__body :deep(pre code) {
  background: none;
  padding: 0;
}

.md__body :deep(blockquote) {
  margin: 0 0 var(--s-3);
  padding-left: var(--s-3);
  border-left: 3px solid var(--c-border-strong);
  color: var(--c-text-muted);
}

.md__body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: var(--s-3);
  font-size: var(--fs-sm);
}

.md__body :deep(th),
.md__body :deep(td) {
  border: 1px solid var(--c-border);
  padding: var(--s-2);
  text-align: left;
}

.md__body :deep(th) {
  background: var(--c-surface-2);
}

.md__body :deep(hr) {
  border: none;
  border-top: 1px solid var(--c-border);
  margin: var(--s-4) 0;
}

.md__fade {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 2.4rem;
  height: 3rem;
  background: linear-gradient(to bottom, transparent, var(--c-surface));
  pointer-events: none;
}

.md__toggle {
  margin-top: var(--s-2);
  background: none;
  border: none;
  padding: var(--s-1) 0;
  color: var(--c-primary);
  font-size: var(--fs-sm);
  font-weight: 600;
  cursor: pointer;
}

.md__toggle:hover {
  text-decoration: underline;
}

.md__caret {
  display: inline-block;
  width: 2px;
  height: 1em;
  vertical-align: text-bottom;
  background: var(--c-primary);
  animation: blink 1s steps(2, start) infinite;
}

@keyframes blink {
  to {
    visibility: hidden;
  }
}
</style>
