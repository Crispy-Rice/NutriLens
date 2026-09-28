<script setup lang="ts">
// Purely presentational: App.vue decides when demo mode is on.
</script>

<template>
  <div class="demo" role="status">
    <div class="demo__inner">
      <span class="badge badge--accent">演示模式</span>
      <p class="demo__text">
        后端尚未配置模型 API Key，当前展示的是内置示例数据，识别结果并非真实分析。
        在 <code>backend/.env</code> 中填入 <code>LLM_API_KEY</code> 后会自动切换到真实模型。
      </p>
    </div>
  </div>
</template>

<style scoped>
.demo {
  background: var(--c-accent-soft);
  border-bottom: 1px solid color-mix(in srgb, var(--c-accent) 30%, transparent);
}

.demo__inner {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  width: 100%;
  max-width: var(--page-max);
  margin: 0 auto;
  padding: var(--s-2) var(--s-4);
}

.demo__text {
  font-size: var(--fs-sm);
  color: var(--c-accent);
}

.demo__text code {
  font-family: var(--font-mono);
  font-size: 0.9em;
  background: color-mix(in srgb, var(--c-accent) 14%, transparent);
  padding: 1px 5px;
  border-radius: var(--r-xs);
}

@media (max-width: 640px) {
  .demo__inner {
    align-items: flex-start;
    flex-direction: column;
    gap: var(--s-1);
  }
}
</style>
