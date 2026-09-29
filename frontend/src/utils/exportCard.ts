/**
 * Save the analysis result locally, in three formats.
 *
 * Everything happens in the browser — no upload, no server round trip. The PNG
 * path serialises the live result card, so what you see is exactly what you get.
 */

import { toPng } from 'html-to-image'
import type { AnalysisResult, DishAnalysis, MealOverall } from '@/types/api'
import { slugifyForFilename } from '@/utils/format'

function timestamp(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}` +
    `-${pad(d.getHours())}${pad(d.getMinutes())}`
  )
}

function baseName(result: AnalysisResult): string {
  return `食鉴-${slugifyForFilename(result.dish_name)}-${timestamp()}`
}

function download(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  // Give the browser a beat to start the download before revoking.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/**
 * Render a DOM node to PNG.
 *
 * `backgroundColor` is set explicitly because the card's background comes from
 * a CSS variable that may resolve to `transparent` in the clone, which would
 * produce a see-through image.
 */
export async function exportResultAsPng(
  node: HTMLElement,
  result: AnalysisResult,
): Promise<void> {
  const dataUrl = await toPng(node, {
    pixelRatio: 2,
    cacheBust: true,
    backgroundColor: getComputedStyle(document.body).backgroundColor || '#ffffff',
  })

  const response = await fetch(dataUrl)
  download(await response.blob(), `${baseName(result)}.png`)
}

export function exportResultAsJson(result: AnalysisResult): void {
  const blob = new Blob([JSON.stringify(result, null, 2)], {
    type: 'application/json;charset=utf-8',
  })
  download(blob, `${baseName(result)}.json`)
}

function dishLines(dish: DishAnalysis, indent = ''): string[] {
  const lines: string[] = []
  const n = dish.nutrition
  const value = (v: number | null, unit: string, digits = 1) =>
    typeof v === 'number' ? `${v.toFixed(digits)}${unit}` : '未知'

  lines.push(`${indent}【${dish.dish_name}】`)
  lines.push(`${indent}识别置信度：${Math.round(dish.confidence * 100)}%`)
  if (dish.confidence_reason) lines.push(`${indent}判断依据：${dish.confidence_reason}`)
  if (dish.dish_name_alternatives.length > 0) {
    lines.push(`${indent}其他可能：${dish.dish_name_alternatives.join('、')}`)
  }

  if (dish.ingredients.length > 0) {
    lines.push(`${indent}— 主要食材 —`)
    for (const item of dish.ingredients) {
      const amount = item.estimated_amount ? `（${item.estimated_amount}）` : ''
      lines.push(`${indent}· ${item.name}${amount}`)
    }
  }

  if (dish.portion_estimate) lines.push(`${indent}估算份量：${dish.portion_estimate}`)

  lines.push(`${indent}— 营养估算 —`)
  lines.push(`${indent}热量：${value(n.calories_kcal, ' kcal', 0)}`)
  lines.push(`${indent}蛋白质：${value(n.protein_g, ' g')}`)
  lines.push(`${indent}脂肪：${value(n.fat_g, ' g')}`)
  lines.push(`${indent}碳水化合物：${value(n.carbs_g, ' g')}`)
  if (typeof n.fiber_g === 'number') lines.push(`${indent}膳食纤维：${n.fiber_g.toFixed(1)} g`)
  if (typeof n.sugar_g === 'number') lines.push(`${indent}糖：${n.sugar_g.toFixed(1)} g`)
  if (typeof n.sodium_mg === 'number') lines.push(`${indent}钠：${n.sodium_mg.toFixed(0)} mg`)
  lines.push(`${indent}估算口径：${n.basis}`)

  if (dish.advice) lines.push(`${indent}— 饮食建议 —`, `${indent}${dish.advice}`)

  if (dish.risk_notes.length > 0) {
    lines.push(`${indent}— 需要注意 —`)
    for (const note of dish.risk_notes) lines.push(`${indent}· ${note}`)
  }

  if (dish.uncertainty_notes.length > 0) {
    lines.push(`${indent}— 不确定的地方 —`)
    for (const note of dish.uncertainty_notes) lines.push(`${indent}· ${note}`)
  }

  return lines
}

function overallLines(overall: MealOverall): string[] {
  const lines = ['— 这一餐的整体构成 —']
  if (overall.summary) lines.push(overall.summary)
  for (const aspect of overall.aspects) {
    const level = aspect.level ? `（${aspect.level}）` : ''
    lines.push(`· ${aspect.label}${level} ${aspect.note}`.trim())
  }
  return lines
}

/** A plain-text summary — the paste-into-a-note version. */
export function buildPlainText(result: AnalysisResult): string {
  const lines: string[] = [
    `【${result.dish_name}】`,
    `分析模式：${result.mode === 'detailed' ? '详细分析' : '快速识别'}`,
  ]

  if (result.images.length > 0) {
    lines.push(`照片数量：${result.images.length} 张`)
  }
  if (result.profile_used) {
    lines.push('本次参考了你的饮食画像（画像内容不会保存）')
  }
  // Stated plainly: without it the numbers below would read as model output.
  if (result.edited) {
    lines.push('※ 识别内容已由用户手动修正；营养数值仍为模型按原始识别估算')
  }

  if (result.overall && (result.overall.summary || result.overall.aspects.length)) {
    lines.push('', ...overallLines(result.overall))
  }

  lines.push('')
  // Primary dish, then the rest of the meal.
  lines.push(...dishLines(result))

  for (const dish of result.additional_dishes) {
    lines.push('', '════ 同餐其他菜品 ════', '')
    lines.push(...dishLines(dish))
  }

  lines.push('', '— 免责声明 —', result.disclaimer)
  lines.push('', `由 食鉴 NutriLens 生成 · ${new Date(result.created_at).toLocaleString()}`)

  return lines.join('\n')
}

export function exportResultAsText(result: AnalysisResult): void {
  const blob = new Blob([buildPlainText(result)], { type: 'text/plain;charset=utf-8' })
  download(blob, `${baseName(result)}.txt`)
}

export async function copyResultAsText(result: AnalysisResult): Promise<void> {
  await navigator.clipboard.writeText(buildPlainText(result))
}
