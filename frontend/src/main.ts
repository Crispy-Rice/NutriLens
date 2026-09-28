import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useAppStore } from '@/stores/app'
import { useProfileStore } from '@/stores/profile'

import './styles/tokens.css'
import './styles/base.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

// Kick off the config/health fetch before first paint so the upload limits and
// demo-mode banner are correct from the very first frame.
void useAppStore(pinia).load()

// The profile lives in this browser; reading it is synchronous but doing it here
// means every page sees it without a loading state.
useProfileStore(pinia).load()

app.mount('#app')
