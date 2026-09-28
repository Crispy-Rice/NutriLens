<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import TagInput from '@/components/TagInput.vue'
import { useConfirm } from '@/composables/useConfirm'
import {
  AGE_BAND_OPTIONS,
  DIETARY_PATTERN_SUGGESTIONS,
  PROFILE_MAX_HEALTH_NOTES,
  SEX_OPTIONS,
  emptyProfile,
  isProfileEmpty,
  useProfileStore,
} from '@/stores/profile'
import type { UserProfile } from '@/types/api'

const store = useProfileStore()
const { confirm } = useConfirm()

const draft = ref<UserProfile>(emptyProfile())
const savedAt = ref<number | null>(null)

// Start from whatever is already stored, and re-sync if it changes elsewhere.
watch(
  () => store.profile,
  (value) => {
    draft.value = JSON.parse(JSON.stringify(value)) as UserProfile
  },
  { immediate: true, deep: true },
)

const isDirty = computed(
  () => JSON.stringify(draft.value) !== JSON.stringify(store.profile),
)

const noteLength = computed(() => draft.value.health_notes?.length ?? 0)

const ALLERGY_SUGGESTIONS = [
  '花生', '坚果', '虾', '蟹', '贝类', '鱼', '鸡蛋', '牛奶', '大豆', '小麦', '芝麻',
]
const AVOIDANCE_SUGGESTIONS = ['香菜', '葱', '姜', '蒜', '动物内脏', '肥肉', '酒精', '咖啡因']
const PREFERENCE_SUGGESTIONS = ['偏清淡', '少油', '少盐', '少辣', '喜酸', '口味偏重', '喜欢汤菜']

function save(): void {
  store.save(draft.value)
  savedAt.value = Date.now()
  window.setTimeout(() => {
    savedAt.value = null
  }, 2600)
}

async function clearAll(): Promise<void> {
  const confirmed = await confirm({
    title: '清除饮食画像？',
    message: '清除后，识别建议将不再参考你的过敏原、忌口与口味偏好。',
    details: [
      '画像只保存在这台设备的浏览器里，清除后无法恢复，需要重新填写。',
      '已经生成过的分析结果不受影响。',
    ],
    confirmLabel: '清除',
  })
  if (!confirmed) return
  store.clear()
  draft.value = emptyProfile()
}

function resetToStored(): void {
  draft.value = JSON.parse(JSON.stringify(store.profile)) as UserProfile
}
</script>

<template>
  <div class="page">
    <header class="head">
      <h1 class="head__title">饮食画像</h1>
      <p class="lede">
        填一份画像，识别建议就能照顾到你的过敏原、忌口和口味偏好。
        全部选填，不填也能正常使用。
      </p>
    </header>

    <section class="card notice">
      <h2 class="card__title">这份画像是什么、不是什么</h2>
      <ul class="points">
        <li>
          <b>它用来筛选和调整建议</b>：比如避开你的过敏原、把做法换成少油版本。
        </li>
        <li>
          <b>它不收集身高体重、也不收集疾病诊断。</b>这个工具给出的营养数字是照片估算，
          支撑不了那种精度，写了反而会引出不可靠的结论。
        </li>
        <li>
          <b>「希望留意的情况」只是给模型看的上下文</b>，不是病史。
          它不会被当作诊断依据，也不会用来推断你的健康状况。
        </li>
        <li>
          <b>它只存在这台设备的浏览器里。</b>不会上传保存，服务端用完即弃；
          分析结果里只会留下「本次参考了画像」这一个标记。
        </li>
      </ul>
    </section>

    <section class="card">
      <h2 class="card__title">过敏原</h2>
      <TagInput
        v-model="draft.allergies"
        label="对哪些食材过敏"
        placeholder="输入后按回车，如：花生"
        hint="如果菜品里含有这些，结果会在「需要注意」里优先提示。"
        :suggestions="ALLERGY_SUGGESTIONS"
      />
    </section>

    <section class="card">
      <h2 class="card__title">忌口与偏好</h2>
      <div class="stack">
        <TagInput
          v-model="draft.avoidances"
          label="不吃的食材"
          placeholder="输入后按回车，如：香菜"
          hint="出于口味或习惯不吃的，会尽量在建议里避开。"
          :suggestions="AVOIDANCE_SUGGESTIONS"
        />

        <TagInput
          v-model="draft.preferences"
          label="口味偏好"
          placeholder="输入后按回车，如：偏清淡"
          hint="影响建议的方向，不影响识别结果。"
          :suggestions="PREFERENCE_SUGGESTIONS"
        />

        <div class="field">
          <label class="field__label" for="dietary-pattern">饮食方式</label>
          <input
            id="dietary-pattern"
            v-model="draft.dietary_pattern"
            class="input"
            type="text"
            list="dietary-pattern-options"
            maxlength="30"
            placeholder="如：素食 / 清真 / 低钠，留空表示无特别"
          />
          <datalist id="dietary-pattern-options">
            <option v-for="option in DIETARY_PATTERN_SUGGESTIONS" :key="option" :value="option" />
          </datalist>
        </div>
      </div>
    </section>

    <section class="card">
      <h2 class="card__title">基本情况（选填）</h2>
      <div class="grid">
        <div class="field">
          <label class="field__label" for="age-band">年龄段</label>
          <select id="age-band" v-model="draft.age_band" class="input">
            <option :value="null">不填</option>
            <option v-for="option in AGE_BAND_OPTIONS" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </div>

        <div class="field">
          <label class="field__label" for="sex">性别</label>
          <select id="sex" v-model="draft.sex" class="input">
            <option :value="null">不填</option>
            <option v-for="option in SEX_OPTIONS" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </div>
      </div>
      <p class="subtle hint">
        这两项只是让建议措辞更贴合，不参与任何计算，也不会被用来评价你。
      </p>
    </section>

    <section class="card">
      <h2 class="card__title">希望留意的情况（选填）</h2>
      <div class="field">
        <textarea
          v-model="draft.health_notes"
          class="textarea"
          rows="3"
          :maxlength="PROFILE_MAX_HEALTH_NOTES"
          placeholder="例如：血脂偏高，医生建议少油；或者在控制糖的摄入"
        ></textarea>
        <p class="subtle hint">
          写在这里的内容会被当作食材层面的筛选依据，例如「油多的做法少推荐」。
          它不会触发任何健康判断、评分或诊断，模型也不会在回复里复述你写的内容。
          <span class="mono">{{ noteLength }}/{{ PROFILE_MAX_HEALTH_NOTES }}</span>
        </p>
      </div>
    </section>

    <div class="actions">
      <button class="btn btn--primary btn--lg" type="button" :disabled="!isDirty" @click="save">
        保存画像
      </button>
      <button v-if="isDirty" class="btn" type="button" @click="resetToStored">
        撤销修改
      </button>
      <button
        v-if="!isProfileEmpty(store.profile)"
        class="btn btn--ghost"
        type="button"
        @click="clearAll"
      >
        清除画像
      </button>
      <p v-if="savedAt" class="saved" role="status">已保存在这台设备上</p>
    </div>
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

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: var(--s-4);
}

.hint {
  margin-top: var(--s-2);
}

.actions {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  flex-wrap: wrap;
}

.saved {
  padding: var(--s-2) var(--s-4);
  border-radius: var(--r-full);
  background: var(--c-primary-soft);
  color: var(--c-primary);
  font-size: var(--fs-sm);
  font-weight: 600;
}

@media (max-width: 560px) {
  .actions {
    flex-direction: column;
    align-items: stretch;
  }

  .saved {
    text-align: center;
  }
}
</style>
