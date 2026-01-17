const SENTINEL_MIN = 1001.0

export function pdvmFloatToDate(pdvmVal: unknown): Date | null {
  if (pdvmVal === null || pdvmVal === undefined) return null
  const num = typeof pdvmVal === 'number' ? pdvmVal : Number(pdvmVal)
  if (!Number.isFinite(num)) return null
  if (Math.abs(num - SENTINEL_MIN) < 1e-6) return null

  // Format: YYYYDDD.Fraction
  const s = num.toFixed(10)
  const [datePart, timePart = '0'] = s.split('.')
  if (datePart.length < 5) return null

  const yyyy = Number(datePart.slice(0, 4))
  const ddd = Number(datePart.slice(4))
  if (!Number.isFinite(yyyy) || !Number.isFinite(ddd) || ddd <= 0) return null

  const base = new Date(yyyy, 0, 1)
  const dayOffset = ddd - 1
  base.setDate(base.getDate() + dayOffset)

  const fraction = Number(`0.${timePart}`)
  if (Number.isFinite(fraction) && fraction > 0) {
    const totalSeconds = Math.round(fraction * 86400)
    base.setSeconds(base.getSeconds() + totalSeconds)
  }

  return base
}

export function formatPdvmDateDE(pdvmVal: unknown, includeTime: boolean = false): string {
  const dt = pdvmFloatToDate(pdvmVal)
  if (!dt) return ''

  const dd = String(dt.getDate()).padStart(2, '0')
  const mm = String(dt.getMonth() + 1).padStart(2, '0')
  const yyyy = String(dt.getFullYear()).padStart(4, '0')

  if (!includeTime) return `${dd}.${mm}.${yyyy}`

  const hh = String(dt.getHours()).padStart(2, '0')
  const mi = String(dt.getMinutes()).padStart(2, '0')
  const ss = String(dt.getSeconds()).padStart(2, '0')

  return `${dd}.${mm}.${yyyy} ${hh}:${mi}:${ss}`
}
