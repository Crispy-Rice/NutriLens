import { ref } from 'vue'

/**
 * Promise-based confirmation dialog.
 *
 * Replaces `window.confirm`, which renders browser chrome, ignores the design
 * tokens, cannot be dark-mode aware, and cannot show what is actually being
 * deleted. Call sites stay a single `await`:
 *
 *     if (!(await confirm({ title: '删除这条记录？' }))) return
 *
 * State lives at module scope so one dialog instance in App.vue serves every
 * caller.
 */

export interface ConfirmOptions {
  title: string
  /** The thing being acted on, shown as a distinct element rather than
   *  embedded mid-sentence — 「删除「无法识别」这条记录」reads badly. */
  subject?: string
  message?: string
  /** Extra context lines, e.g. what exactly disappears. */
  details?: string[]
  confirmLabel?: string
  cancelLabel?: string
}

interface ConfirmState extends ConfirmOptions {
  open: boolean
}

const state = ref<ConfirmState>({ open: false, title: '' })

let resolver: ((confirmed: boolean) => void) | null = null

function settle(confirmed: boolean): void {
  if (!state.value.open) return
  state.value.open = false
  const resolve = resolver
  resolver = null
  resolve?.(confirmed)
}

export function useConfirm() {
  function confirm(options: ConfirmOptions): Promise<boolean> {
    // If one is somehow already open, treat it as cancelled rather than
    // leaving its promise dangling forever.
    if (resolver) settle(false)

    state.value = { ...options, open: true }
    return new Promise<boolean>((resolve) => {
      resolver = resolve
    })
  }

  return { state, confirm, settle }
}
