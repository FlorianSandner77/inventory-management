// Restocking recommendation logic (pure functions, no Vue or API dependencies)

// Forecast items worth restocking: anything not trending down
export function getEligibleForecasts(forecasts) {
  return forecasts.filter(f => f.trend !== 'decreasing')
}

// Forecast growth as a fraction (0.5 = +50%). Guards against a zero baseline
// so a missing current demand can't produce Infinity/NaN and break the ranking.
export function getGrowth(forecast) {
  if (!forecast.current_demand) return 0
  return (forecast.forecasted_demand - forecast.current_demand) / forecast.current_demand
}

// Cost of buying the full forecasted demand for every eligible item
export function getFullCoverageCost(forecasts) {
  return getEligibleForecasts(forecasts)
    .reduce((sum, f) => sum + f.forecasted_demand * f.unit_cost, 0)
}

// Recommend items to restock within a budget.
// Items are ranked by forecast growth (highest first). Each is bought whole
// (quantity = forecasted demand for the period) if it fits the remaining
// budget; otherwise it is skipped and the walk continues, so cheaper items
// further down the ranking can still be afforded.
export function recommendRestock(forecasts, budget) {
  const ranked = getEligibleForecasts(forecasts)
    .slice()
    .sort((a, b) => getGrowth(b) - getGrowth(a) || a.item_sku.localeCompare(b.item_sku))

  const items = []
  let remaining = Math.max(budget, 0)

  for (const forecast of ranked) {
    const quantity = forecast.forecasted_demand
    const lineTotal = quantity * forecast.unit_cost
    if (quantity > 0 && lineTotal <= remaining) {
      items.push({ ...forecast, quantity, lineTotal })
      remaining -= lineTotal
    }
  }

  const total = items.reduce((sum, item) => sum + item.lineTotal, 0)
  return { items, total, remaining }
}
