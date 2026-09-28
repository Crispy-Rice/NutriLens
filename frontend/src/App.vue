<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import AppHeader from '@/components/AppHeader.vue'
import DemoBanner from '@/components/DemoBanner.vue'
import AppFooter from '@/components/AppFooter.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { useAppStore } from '@/stores/app'

const app = useAppStore()
const route = useRoute()

// Keep the footer disclaimer on every screen, but the About page already
// explains it at length, so avoid repeating it there.
const showFooterDisclaimer = computed(() => route.name !== 'about')
</script>

<template>
  <div class="shell">
    <AppHeader />
    <DemoBanner v-if="app.demoMode" />

    <main class="shell__main">
      <RouterView v-slot="{ Component }">
        <component :is="Component" />
      </RouterView>
    </main>

    <AppFooter v-if="showFooterDisclaimer" />

    <!-- One dialog instance serves every confirm() caller. -->
    <ConfirmDialog />
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  min-height: 100dvh;
}

.shell__main {
  flex: 1;
}
</style>
