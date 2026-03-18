const SENTINEL_MIN = 1001.0

export function dateToPdvmFloat(value: Date | number | string): number | null {
  const dt = value instanceof Date ? value : new Date(value)
  if (!(dt instanceof Date) || Number.isNaN(dt.getTime())) return null

  const year = dt.getFullYear()
  const start = new Date(year, 0, 1)

  const dayOfYear = Math.floor((dt.getTime() - start.getTime()) / 86400000) + 1
  if (!Number.isFinite(dayOfYear) || dayOfYear <= 0) return null

  const secondsOfDay = dt.getHours() * 3600 + dt.getMinutes() * 60 + dt.getSeconds()
  const fraction = secondsOfDay / 86400

  const base = Number(`${year}${String(dayOfYear).padStart(3, '0')}`)
  return Number((base + fraction).toFixed(5))
}

export function pdvmNowFloat(): number {
  return dateToPdvmFloat(new Date()) ?? SENTINEL_MIN
}

export function pdvmFloatToDate(pdvmVal: unknown): Date | null {
  if (pdvmVal === null || pdvmVal === undefined) return null
  const num = typeof pdvmVal === 'number' ? pdvmVal : Number(pdvmVal)
  if (!Number.isFinite(num)) return null
  if (Math.abs(num - SENTINEL_MIN) < 1e-6) return null

  const s = num.toFixed(10)
  const datePartFromRaw = typeof pdvmVal === 'string' ? String(pdvmVal).trim().split('.')[0] : ''
  const datePart = datePartFromRaw || s.split('.')[0]
  const [, timePartFixed = '0'] = s.split('.')
  if (datePart.length < 5) return null

  const yyyy = Number(datePart.slice(0, 4))
  const ddd = Number(datePart.slice(4))
  if (!Number.isFinite(yyyy) || !Number.isFinite(ddd) || ddd <= 0) return null

  const base = new Date(yyyy, 0, 1)
  const dayOffset = ddd - 1
  base.setDate(base.getDate() + dayOffset)

  // Canonical decoding: day fraction (YYYYDDD.FRACTION)
  const fraction = Number(`0.${timePartFixed}`)
  if (Number.isFinite(fraction) && fraction >= 0) {
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
