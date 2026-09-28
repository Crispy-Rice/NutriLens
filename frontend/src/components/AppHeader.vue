<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'

const app = useAppStore()
const route = useRoute()

const links = [
  { name: 'home', label: '识别' },
  { name: 'chat', label: '对话' },
  { name: 'history', label: '历史' },
  { name: 'profile', label: '画像' },
  { name: 'about', label: '关于' },
]

const statusLabel = computed(() => {
  if (app.loading) return '连接中'
  if (!app.backendReachable) return '服务未连接'
  if (app.health?.database !== 'ok') return '存储异常'
  return '服务正常'
})

const statusTone = computed(() => {
  if (app.loading) return 'wait'
  if (!app.backendReachable) return 'bad'
  if (app.health?.database !== 'ok') return 'warn'
  return 'good'
})
</script>

<template>
  <header class="hdr">
    <div class="hdr__inner">
      <RouterLink to="/" class="brand" aria-label="食鉴 NutriLens 首页">
        <span class="brand__mark" aria-hidden="true">
          <svg viewBox="0 0 32 32" width="30" height="30" fill="none">
            <path
              d="M16 28c0-8 4.5-13 12-15-1 8.5-5 13.5-12 15Z"
              fill="currentColor"
              opacity="0.85"
            />
            <path
              d="M16 28C16 20 11.5 15 4 13c1 8.5 5 13.5 12 15Z"
              fill="currentColor"
              opacity="0.55"
            />
            <path
              d="M16 28V13"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
            />
          </svg>
        </span>
        <span class="brand__text">
          <strong>食鉴</strong>
          <span class="brand__sub">NutriLens</span>
        </span>
      </RouterLink>

      <nav class="nav" aria-label="主导航">
        <RouterLink
          v-for="link in links"
          :key="link.name"
          :to="{ name: link.name }"
          class="nav__link"
          :class="{ 'nav__link--active': route.name === link.name }"
        >
          {{ link.label }}
        </RouterLink>
      </nav>

      <p class="status" :class="`status--${statusTone}`" :title="app.health?.llm_model">
        <span class="status__dot" aria-hidden="true"></span>
        <span class="status__text">{{ statusLabel }}</span>
      </p>
    </div>
  </header>
</template>

<style scoped>
.hdr {
  position: sticky;
  top: 0;
  z-index: 20;
  background: color-mix(in srgb, var(--c-bg) 88%, transparent);
  backdrop-filter: saturate(1.4) blur(12px);
  border-bottom: 1px solid var(--c-border);
}

.hdr__inner {
  display: flex;
  align-items: center;
  gap: var(--s-4);
  width: 100%;
  max-width: var(--page-max);
  margin: 0 auto;
  padding: var(--s-3) var(--s-4);
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: var(--tap-min);
  color: var(--c-text);
  text-decoration: none;
  margin-right: auto;
}

.brand__mark {
  color: var(--c-primary);
  display: grid;
  place-items: center;
}

.brand__text {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}

.brand__text strong {
  font-size: var(--fs-lg);
  letter-spacing: 0.04em;
}

.brand__sub {
  font-size: 0.6875rem;
  color: var(--c-text-subtle);
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.nav {
  display: flex;
  gap: var(--s-1);
}

.nav__link {
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-sm);
  color: var(--c-text-muted);
  text-decoration: none;
  font-size: var(--fs-base);
  font-weight: 550;
  min-height: var(--tap-min);
  display: inline-flex;
  align-items: center;
  transition: background var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease);
}

.nav__link:hover {
  background: var(--c-surface-2);
  color: var(--c-text);
}

.nav__link--active {
  background: var(--c-primary-soft);
  color: var(--c-primary);
}

.status {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  font-size: var(--fs-xs);
  color: var(--c-text-subtle);
  padding-left: var(--s-3);
  border-left: 1px solid var(--c-border);
}

.status__dot {
  width: 7px;
  height: 7px;
  border-radius: var(--r-full);
  background: var(--c-text-subtle);
  flex: none;
}

.status--good .status__dot {
  background: var(--c-primary);
}
.status--warn .status__dot {
  background: var(--c-warn);
}
.status--bad .status__dot {
  background: var(--c-danger);
}
.status--wait .status__dot {
  background: var(--c-accent);
}

/* Below 640px the status text would squeeze the nav; the dot still conveys it. */
@media (max-width: 640px) {
  .status__text {
    display: none;
  }
  .status {
    padding-left: var(--s-2);
  }
  .brand__sub {
    display: none;
  }
  .nav__link {
    padding: var(--s-2);
  }
}
</style>
