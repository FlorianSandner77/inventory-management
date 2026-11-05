<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card budget-card">
        <div class="budget-header">
          <label class="budget-label" for="budget-slider">{{ t('restocking.budgetLabel') }}</label>
          <div class="budget-value">{{ money(budget) }}</div>
        </div>
        <input
          id="budget-slider"
          v-model.number="budget"
          class="budget-slider"
          type="range"
          min="0"
          :max="maxBudget"
          step="500"
        />
        <div class="budget-scale">
          <span>{{ money(0) }}</span>
          <span>{{ money(maxBudget) }}</span>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.summary.budget') }}</div>
          <div class="stat-value">{{ money(budget) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.summary.spent') }}</div>
          <div class="stat-value">{{ money(totalSpent) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.summary.remaining') }}</div>
          <div class="stat-value">{{ money(remaining) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.summary.leadTime') }}</div>
          <div class="stat-value">{{ t('restocking.summary.days', { count: orderLeadTime }) }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header restock-header">
          <h3 class="card-title">{{ t('restocking.recommendedItems') }} ({{ includedItems.length }}/{{ recommendation.items.length }})</h3>
          <button
            type="button"
            class="place-order-btn"
            :disabled="includedItems.length === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="successMessage" class="message success-message" role="status">{{ successMessage }}</div>
        <div v-if="submitError" class="message error-message" role="alert">{{ submitError }}</div>

        <div v-if="recommendation.items.length === 0" class="empty-state">{{ t('restocking.empty') }}</div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.include') }}</th>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.supplier') }}</th>
                <th>{{ t('restocking.table.quantity') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineTotal') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in recommendation.items"
                :key="item.item_sku"
                :class="{ excluded: excludedSkus.has(item.item_sku) }"
              >
                <td>
                  <input
                    type="checkbox"
                    :checked="!excludedSkus.has(item.item_sku)"
                    :aria-label="t('restocking.includeItem', { sku: item.item_sku })"
                    :disabled="submitting"
                    @change="toggleItem(item.item_sku)"
                  />
                </td>
                <td><strong>{{ item.item_sku }}</strong></td>
                <td>{{ translateProductName(item.item_name) }}</td>
                <td>
                  <span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
                </td>
                <td>{{ item.supplier }}</td>
                <td>{{ item.quantity.toLocaleString() }}</td>
                <td>{{ moneyDecimals(item.unit_cost) }}</td>
                <td><strong>{{ moneyDecimals(item.lineTotal) }}</strong></td>
                <td>{{ item.lead_time_days }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="recommendation.items.length > 0 && includedItems.length === 0" class="empty-state">
          {{ t('restocking.noneSelected') }}
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'
import { getFullCoverageCost, recommendRestock } from '../utils/restocking'

const BUDGET_STEP = 500

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, translateProductName } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const forecasts = ref([])
    const budget = ref(0)

    // Excluded (not included) SKUs are tracked instead of included ones so that
    // moving the slider, which changes the recommended set, keeps the user's unchecks.
    const excludedSkus = ref(new Set())

    const submitting = ref(false)
    const submitError = ref(null)
    const successMessage = ref(null)

    // Slider max: cost of full coverage rounded up to the slider step so the
    // top of the range always affords everything. At least one step to avoid a zero-width slider.
    const maxBudget = computed(() => {
      const cost = Math.ceil(getFullCoverageCost(forecasts.value))
      return Math.max(Math.ceil(cost / BUDGET_STEP) * BUDGET_STEP, BUDGET_STEP)
    })

    const recommendation = computed(() => recommendRestock(forecasts.value, budget.value))

    const includedItems = computed(() =>
      recommendation.value.items.filter(item => !excludedSkus.value.has(item.item_sku))
    )

    // Summary figures come from included items only, not the raw recommendation
    const totalSpent = computed(() =>
      includedItems.value.reduce((sum, item) => sum + item.lineTotal, 0)
    )
    const remaining = computed(() => budget.value - totalSpent.value)

    // Order lead time is bound by the slowest supplier among included items
    const orderLeadTime = computed(() =>
      includedItems.value.reduce((max, item) => Math.max(max, item.lead_time_days), 0)
    )

    const money = (amount) => formatCurrency(amount, currentCurrency.value)
    const moneyDecimals = (amount) => formatCurrencyWithDecimals(amount, currentCurrency.value, 2)

    const toggleItem = (sku) => {
      // Replace the Set so the ref change is always detected
      const next = new Set(excludedSkus.value)
      if (next.has(sku)) next.delete(sku)
      else next.add(sku)
      excludedSkus.value = next
    }

    const loadForecasts = async () => {
      try {
        loading.value = true
        error.value = null
        forecasts.value = await api.getDemandForecasts()
        // Default to roughly half of full coverage, snapped to the slider step
        budget.value = Math.round(maxBudget.value / 2 / BUDGET_STEP) * BUDGET_STEP
      } catch (err) {
        error.value = t('restocking.loadError') + ': ' + err.message
        console.error('Load error:', err)
      } finally {
        loading.value = false
      }
    }

    const placeOrder = async () => {
      // Guard against double submit (button is also disabled while submitting)
      if (submitting.value || includedItems.value.length === 0) return
      submitting.value = true
      submitError.value = null
      successMessage.value = null
      try {
        const order = await api.createRestockingOrder({
          items: includedItems.value.map(i => ({ sku: i.item_sku, quantity: i.quantity }))
        })
        successMessage.value = t('restocking.success', {
          orderNumber: order.order_number,
          count: order.lead_time_days
        })
      } catch (err) {
        // Backend returns { detail } on 400/404
        submitError.value = err.response?.data?.detail || err.message || t('restocking.error')
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadForecasts)

    return {
      t,
      translateProductName,
      loading,
      error,
      budget,
      maxBudget,
      excludedSkus,
      recommendation,
      includedItems,
      totalSpent,
      remaining,
      orderLeadTime,
      submitting,
      submitError,
      successMessage,
      money,
      moneyDecimals,
      toggleItem,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-card {
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.budget-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 1rem;
}

.budget-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.budget-value {
  font-size: 2rem;
  font-weight: 700;
  color: #0f172a;
}

.budget-slider {
  width: 100%;
  accent-color: #0f172a;
}

.budget-scale {
  display: flex;
  justify-content: space-between;
  font-size: 0.813rem;
  color: #64748b;
  margin-top: 0.5rem;
}

.restock-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.place-order-btn {
  background: #0f172a;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
}

.place-order-btn:hover:not(:disabled) {
  background: #1e293b;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.message {
  margin: 0 1.5rem 1rem;
  padding: 0.75rem 1rem;
  border-radius: 6px;
  font-size: 0.875rem;
}

.success-message {
  background: #d1fae5;
  color: #065f46;
}

.error-message {
  background: #fee2e2;
  color: #991b1b;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}

tr.excluded td {
  opacity: 0.5;
}
</style>
