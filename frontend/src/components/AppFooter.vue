<script setup lang="ts">
import { useAppStore } from '@/stores/app'

const app = useAppStore()
</script>

<template>
  <footer class="ftr">
    <div class="ftr__inner">
      <p class="ftr__disclaimer">{{ app.disclaimer }}</p>
      <p class="subtle">
        食鉴 NutriLens v{{ app.config?.version ?? '0.1.0' }} ·
        <RouterLink to="/about">关于与隐私</RouterLink>
      </p>
    </div>
  </footer>
</template>

<style scoped>
.ftr {
  border-top: 1px solid var(--c-border);
  background: var(--c-bg-tint);
}

.ftr__inner {
  width: 100%;
  max-width: var(--page-max);
  margin: 0 auto;
  padding: var(--s-5) var(--s-4);
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.ftr__disclaimer {
  font-size: var(--fs-sm);
  color: var(--c-text-muted);
  max-width: 68ch;
}
</style>
