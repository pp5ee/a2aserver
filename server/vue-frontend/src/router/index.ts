import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import HomeView from '@/views/HomeView.vue'
import ConversationView from '@/views/ConversationView.vue'
import SettingsView from '@/views/SettingsView.vue'
import AgentsView from '@/views/AgentsView.vue'

const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    name: 'home',
    component: HomeView
  },
  {
    path: '/conversation',
    name: 'conversation',
    component: ConversationView
  },
  {
    path: '/settings',
    name: 'settings',
    component: SettingsView
  },
  {
    path: '/agents',
    name: 'agents',
    component: AgentsView
  }
]

const router = createRouter({
  history: createWebHistory(process.env.BASE_URL),
  routes
})

export default router 