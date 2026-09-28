import { ref, type Ref } from 'vue'
import type { AnalysisResult } from '@/types/api'
import {
  copyResultAsText,
  exportResultAsJson,
  exportResultAsPng,
  exportResultAsText,
} from '@/utils/exportCard'

/**
 * The save/copy actions for a result, shared by the standalone result card and
 * the analysis panels inside a conversation. `cardRef` is the node the PNG is
 * rendered from, so each caller exports its own card.
 */
export function useResultExport(
  getResult: () => AnalysisResult | null,
  cardRef: Ref<HTMLElement | null>,
) {
  const savingPng = ref(false)
  const notice = ref<string | null>(null)

  function flash(message: string): void {
    notice.value = message
    window.setTimeout(() => {
      notice.value = null
    }, 2600)
  }

  async function savePng(): Promise<void> {
    const result = getResult()
    if (!result || !cardRef.value || savingPng.value) return
    savingPng.value = true
    try {
      await exportResultAsPng(cardRef.value, result)
      flash('结果卡已保存为图片')
    } catch {
      flash('图片导出失败，可以改用 JSON 或文本格式')
    } finally {
      savingPng.value = false
    }
  }

  function saveJson(): void {
    const result = getResult()
    if (!result) return
    exportResultAsJson(result)
    flash('已保存结构化 JSON')
  }

  function saveText(): void {
    const result = getResult()
    if (!result) return
    exportResultAsText(result)
    flash('已保存文本摘要')
  }

  async function copyText(): Promise<void> {
    const result = getResult()
    if (!result) return
    try {
      await copyResultAsText(result)
      flash('已复制到剪贴板')
    } catch {
      flash('复制失败，请改用保存为文本')
    }
  }

  return { savingPng, notice, savePng, saveJson, saveText, copyText }
}
