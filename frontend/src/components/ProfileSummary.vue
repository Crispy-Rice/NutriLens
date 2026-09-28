<script setup lang="ts">
import { useProfileStore } from '@/stores/profile'

const store = useProfileStore()
</script>

<template>
  <section class="card profile">
    <div class="profile__head">
      <h2 class="card__title">
        饮食画像
        <span v-if="store.isSet" class="badge badge--primary">已设为参考</span>
        <span v-else class="badge">未设置</span>
      </h2>
      <RouterLink class="btn btn--ghost" :to="{ name: 'profile' }">
        {{ store.isSet ? '编辑' : '去设置' }}
      </RouterLink>
    </div>

    <template v-if="store.isSet">
      <dl class="rows">
        <div v-for="row in store.summary" :key="row.label" class="rows__row">
          <dt>{{ row.label }}</dt>
          <dd>
            <span v-for="value in row.values" :key="value" class="badge">{{ value }}</span>
          </dd>
        </div>
      </dl>
      <p class="subtle">
        识别时会参考以上信息。画像只保存在这台设备的浏览器里，不会上传存储。
      </p>
    </template>

    <p v-else class="muted">
      填一份饮食画像（过敏原、忌口、偏好），建议会更贴合你。全部选填，
      只保存在这台设备上。
    </p>
  </section>
</template>

<style scoped>
.profile {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.profile__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  flex-wrap: wrap;
}

.profile__head .card__title {
  margin-bottom: 0;
}

.rows {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.rows__row {
  display: grid;
  grid-template-columns: 6rem 1fr;
  gap: var(--s-3);
  align-items: baseline;
}

.rows__row dt {
  color: var(--c-text-subtle);
  font-size: var(--fs-sm);
}

.rows__row dd {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-1);
}

@media (max-width: 560px) {
  .rows__row {
    grid-template-columns: 1fr;
    gap: var(--s-1);
  }
}
</style>
