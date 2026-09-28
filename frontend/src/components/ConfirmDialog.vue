<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useConfirm } from '@/composables/useConfirm'

const { state, settle } = useConfirm()

const panelRef = ref<HTMLElement | null>(null)
const cancelRef = ref<HTMLButtonElement | null>(null)

// Restore focus to whatever opened the dialog, so keyboard users are not
// dropped back at the top of the page.
let previouslyFocused: HTMLElement | null = null

function focusables(): HTMLElement[] {
  const panel = panelRef.value
  if (!panel) return []
  return Array.from(
    panel.querySelectorAll<HTMLElement>('button, [href], input, [tabindex]:not([tabindex="-1"])'),
  ).filter((el) => !el.hasAttribute('disabled'))
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    event.preventDefault()
    settle(false)
    return
  }
  if (event.key !== 'Tab') return

  // Keep focus inside the dialog while it is open.
  const items = focusables()
  if (items.length === 0) return
  const first = items[0]
  const last = items[items.length - 1]
  const active = document.activeElement as HTMLElement | null

  if (event.shiftKey && (active === first || !panelRef.value?.contains(active))) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}

function onBackdropClick(event: MouseEvent): void {
  // Only a click on the backdrop itself, not one that bubbled from the panel.
  if (event.target === event.currentTarget) settle(false)
}

watch(
  () => state.value.open,
  async (open) => {
    if (open) {
      previouslyFocused = document.activeElement as HTMLElement | null
      document.body.style.overflow = 'hidden'
      await nextTick()
      // Cancel is focused first: destructive actions should not be one Enter
      // keypress away.
      cancelRef.value?.focus()
    } else {
      document.body.style.overflow = ''
      previouslyFocused?.focus?.()
      previouslyFocused = null
    }
  },
)

onBeforeUnmount(() => {
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <Transition name="confirm">
      <div
        v-if="state.open"
        class="backdrop"
        @click="onBackdropClick"
        @keydown="onKeydown"
      >
        <div
          ref="panelRef"
          class="panel"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="confirm-title"
          :aria-describedby="state.message || state.details ? 'confirm-body' : undefined"
        >
          <h2 id="confirm-title" class="panel__title">{{ state.title }}</h2>

          <!-- The subject gets its own line. Inlining it reads badly when the
               name is something like 「无法识别」. -->
          <p v-if="state.subject" class="panel__subject">{{ state.subject }}</p>

          <div v-if="state.message || state.details" id="confirm-body" class="panel__body">
            <p v-if="state.message" class="panel__message">{{ state.message }}</p>
            <ul v-if="state.details?.length" class="panel__details">
              <li v-for="line in state.details" :key="line">{{ line }}</li>
            </ul>
          </div>

          <div class="panel__actions">
            <button ref="cancelRef" class="btn" type="button" @click="settle(false)">
              {{ state.cancelLabel || '取消' }}
            </button>
            <button class="btn btn--danger" type="button" @click="settle(true)">
              {{ state.confirmLabel || '确定' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: grid;
  place-items: center;
  padding: var(--s-4);
  background: rgba(16, 21, 16, 0.42);
  backdrop-filter: blur(3px);
}

.panel {
  width: 100%;
  max-width: 26rem;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  padding: var(--s-5);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  box-shadow: var(--sh-3);
}

.panel__title {
  font-size: var(--fs-lg);
}

.panel__subject {
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-sm);
  background: var(--c-surface-2);
  border-left: 3px solid var(--c-danger);
  font-weight: 600;
  overflow-wrap: anywhere;
}

.panel__body {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.panel__message {
  color: var(--c-text-muted);
  font-size: var(--fs-base);
}

.panel__details {
  padding-left: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  color: var(--c-text-subtle);
  font-size: var(--fs-sm);
}

.panel__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--s-2);
  margin-top: var(--s-1);
}

/* The destructive action carries the danger colour; the safe one is the
   default-styled button. */
.btn--danger {
  background: var(--c-danger);
  color: #fff;
}

.btn--danger:hover:not(:disabled) {
  background: color-mix(in srgb, var(--c-danger) 85%, #000);
}

.confirm-enter-active,
.confirm-leave-active {
  transition: opacity var(--dur) var(--ease);
}

.confirm-enter-active .panel,
.confirm-leave-active .panel {
  transition: transform var(--dur) var(--ease);
}

.confirm-enter-from,
.confirm-leave-to {
  opacity: 0;
}

.confirm-enter-from .panel,
.confirm-leave-to .panel {
  transform: translateY(8px) scale(0.98);
}

@media (max-width: 560px) {
  .backdrop {
    align-items: end;
    padding: 0;
  }

  /* Slides up from the bottom, closer to a native sheet on a phone. */
  .panel {
    max-width: none;
    border-bottom-left-radius: 0;
    border-bottom-right-radius: 0;
    padding-bottom: calc(var(--s-5) + env(safe-area-inset-bottom, 0px));
  }

  .panel__actions {
    flex-direction: column-reverse;
  }

  .panel__actions .btn {
    width: 100%;
  }
}
</style>
