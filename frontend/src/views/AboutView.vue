<script setup lang="ts">
import { useAppStore } from '@/stores/app'

const app = useAppStore()
</script>

<template>
  <div class="page">
    <header class="head">
      <h1 class="head__title">关于与隐私</h1>
      <p class="lede">
        食鉴是一个食物营养识别工具。它的目标是帮你在吃饭前对眼前这一餐有个大致概念，
        而不是替你做健康决定。
      </p>
    </header>

    <section class="card">
      <h2 class="card__title">你的图片会怎样被处理</h2>
      <ul class="points">
        <li>
          图片<b>只用于本次分析</b>。服务端在处理结束后即删除，不会长期保存。
        </li>
        <li>
          上传前，浏览器会先在本地压缩图片；服务端收到后再做一次校验、方向校正与缩放。
        </li>
        <li>
          重新编码的过程会<b>一并抹掉照片的 EXIF 信息</b>，包括拍摄地点定位，
          因此这些信息不会随图片进入识别环节。
        </li>
        <li>
          服务端日志<b>不记录图片内容</b>、base64 数据或 API Key；
          日志里做了脱敏处理。
        </li>
        <li>
          「历史记录」只保存<b>结构化的分析结果</b>（菜品名、营养估算等），
          <b>不保存原始图片</b>。你可以随时删除任意一条记录。
        </li>
        <li>
          临时文件设有过期时间，服务端会定期清理超过时限的残留文件。
        </li>
        <li>
          整个应用不接入任何第三方统计或广告脚本，图片不会被发送到本服务以外的位置
          （识别所需的模型调用除外）。
        </li>
      </ul>
    </section>

    <section class="card">
      <h2 class="card__title">这个工具的边界</h2>
      <ul class="points">
        <li>
          <b>不提供健康评分。</b>你不会在这里看到「健康分 88」这类数字——
          单张照片无法支撑那种结论，给出它只会制造虚假的权威感。
        </li>
        <li>
          <b>不做医疗或营养诊断。</b>本工具不判断疾病风险，也不替代医生或注册营养师。
        </li>
        <li>
          <b>不评价你。</b>建议只针对食物本身，不涉及你的体型、体重、饮食习惯或生活方式。
        </li>
        <li>
          <b>份量与营养都是估算。</b>拍照角度、遮挡、烹饪用油、实际克重都会影响结果，
          同一道菜不同做法的差异可能很大。
        </li>
        <li>
          结果中会显示<b>置信度</b>。当模型不太确定时，会明确提示你确认菜品或重新拍摄，
          你也可以根据候选名称自行判断。
        </li>
      </ul>
    </section>

    <section class="card notice">
      <h2 class="card__title">免责声明</h2>
      <p>{{ app.disclaimer }}</p>
      <p v-if="app.health" class="subtle">
        当前识别引擎：<span class="mono">{{ app.health.llm_model }}</span>
        <template v-if="app.demoMode">（演示模式，返回的是内置示例数据）</template>
      </p>
    </section>
  </div>
</template>

<style scoped>
.head {
  margin-bottom: var(--s-5);
  max-width: 62ch;
}

.head__title {
  font-size: var(--fs-2xl);
  margin-bottom: var(--s-3);
}

.lede {
  color: var(--c-text-muted);
  font-size: var(--fs-md);
}

.page > * + * {
  margin-top: var(--s-4);
}

.points {
  padding-left: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.points li {
  color: var(--c-text-muted);
}

.points b {
  color: var(--c-text);
  font-weight: 600;
}

.notice {
  background: var(--c-surface-2);
}
</style>
