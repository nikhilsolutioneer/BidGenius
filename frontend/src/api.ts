import { getLanguage, getLocale } from './i18n';

export class ApiError extends Error {
  status: number;
  details: unknown;
  constructor(status: number, detail: unknown) {
    super(
      typeof detail === 'string'
        ? detail
        : (detail as { message?: string })?.message || JSON.stringify(detail),
    );
    this.status = status;
    this.details = detail;
  }
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const actor = localStorage.getItem('bidgenius_actor') || 'Local estimator';
  const r = await fetch(`/api${path}`, {
    ...options,
    headers:
      options.body instanceof FormData
        ? { 'X-Actor': actor, ...options.headers }
        : { 'Content-Type': 'application/json', 'X-Actor': actor, ...options.headers },
  });
  if (!r.ok) {
    let detail: unknown;
    try {
      detail = (await r.json()).detail;
    } catch {
      detail = await r.text();
    }
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<T>;
}
export const post = <T>(path: string, body: unknown = {}) =>
  api<T>(path, { method: 'POST', body: JSON.stringify(body) });
export const patch = <T>(path: string, body: unknown) =>
  api<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
const decimalParts = (value: unknown): [bigint, number] | null => {
  if (value === null || value === undefined || value === '') return null;
  const match = String(value).trim().match(/^(-?)(\d+)(?:\.(\d+))?$/);
  if (!match) return null;
  const fraction = match[3] || '';
  const units = BigInt(match[2] + fraction) * (match[1] ? -1n : 1n);
  return [units, fraction.length];
};
const pow10 = (n: number) => 10n ** BigInt(n);
const roundUnits = (units: bigint, from: number, to: number) => {
  if (to >= from) return units * pow10(to - from);
  const divisor = pow10(from - to);
  const magnitude = (units < 0n ? -units : units) + divisor / 2n;
  return (units < 0n ? -1n : 1n) * (magnitude / divisor);
};
const numberSymbols = () => new Intl.NumberFormat(getLocale()).formatToParts(1234.5);
const grouped = (v: bigint) => v.toString().replace(/\B(?=(\d{3})+(?!\d))/g,
  numberSymbols().find(part => part.type === 'group')?.value || '’');
export const formatDecimal = (value: unknown, digits = 2, fixed = false): string | null => {
  const parts = decimalParts(value);
  if (!parts) return null;
  const rounded = roundUnits(parts[0], parts[1], digits);
  const abs = rounded < 0n ? -rounded : rounded;
  const whole = abs / pow10(digits);
  const frac = digits ? (abs % pow10(digits)).toString().padStart(digits, '0') : '';
  const trimmed = fixed ? frac : frac.replace(/0+$/, '');
  const decimal = numberSymbols().find(part => part.type === 'decimal')?.value || '.';
  return `${rounded < 0n ? '-' : ''}${grouped(whole)}${trimmed ? `${decimal}${trimmed}` : ''}`;
};
export const money = (value: unknown, digits = 0) => {
  const result = formatDecimal(value, digits, true);
  return result === null ? 'Unpriced' : `CHF ${result}`;
};
export const number = (value: unknown, digits = 2) => formatDecimal(value, digits) ?? '—';
export const compareDecimal = (a: unknown, b: unknown) => {
  const left = decimalParts(a);
  const right = decimalParts(b);
  if (!left || !right) return left ? 1 : right ? -1 : 0;
  const scale = Math.max(left[1], right[1]);
  const l = roundUnits(left[0], left[1], scale);
  const r = roundUnits(right[0], right[1], scale);
  return l < r ? -1 : l > r ? 1 : 0;
};
export const percentOf = (part: unknown, whole: unknown, digits = 1) => {
  const p = decimalParts(part);
  const w = decimalParts(whole);
  if (!p || !w || w[0] === 0n) return '0';
  const numerator = p[0] * pow10(w[1]) * 100n * pow10(digits);
  const denominator = w[0] * pow10(p[1]);
  const sign = numerator < 0n !== denominator < 0n ? -1n : 1n;
  const abs = (numerator < 0n ? -numerator : numerator) + (denominator < 0n ? -denominator : denominator) / 2n;
  const quotient = sign * (abs / (denominator < 0n ? -denominator : denominator));
  const raw = (quotient < 0n ? -quotient : quotient).toString().padStart(digits + 1, '0');
  const display = digits ? `${raw.slice(0, -digits)}.${raw.slice(-digits)}` : raw;
  return `${quotient < 0n ? '-' : ''}${display}`;
};
export const probabilityPercent = (value: unknown, digits = 1) => percentOf(value, '1', digits);
const labelOverrides: Record<string, string> = {
  airflow_m3h: 'Airflow (m³/h)',
  width_mm: 'Width (mm)',
  height_mm: 'Height (mm)',
  diameter_mm: 'Diameter (mm)',
  angle_deg: 'Angle (°)',
  fire_class: 'Fire rating',
  AHU_LARGE: 'Large air handling unit',
  DUCT_RECT: 'Rectangular duct installation',
  DUCT_ROUND: 'Round duct installation',
  DUCT_FITTING: 'Duct fitting installation',
  rect_duct_area_rate_enabled: 'Straight duct catalogue area rate',
  lt_area_rate_enabled: 'LT fitting area-rate assumption',
  fitting_section_area_factor: 'LT fitting area factor',
  full_draft_v1: 'Draft estimate',
  policy: 'Estimate basis',
  proxy: 'Similar catalogue item',
  pricing_proxy: 'Rate from similar catalogue item',
  spans: 'Source lines',
  source_spans: 'Source lines',
  unassigned_blocks: 'Text not yet assigned to a position',
};
export const label = (v: string) =>
  labelOverrides[v] ||
  v
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
export const humanEvidence = (value: string) => value
  .replace(/airflow_m3h|width_mm|height_mm|diameter_mm|angle_deg|fire_class/g, (key) => label(key))
  .replace(/\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b/g, (key) => label(key))
  .replace(/\bUnit: m2\b/g, 'Unit: m²');
export const date = (v?: string | null) =>
  v
    ? new Intl.DateTimeFormat(getLanguage() === 'de' ? 'de-CH' : 'en-GB', {
        dateStyle: 'medium',
        timeStyle: 'short',
        timeZone: 'Europe/Zurich',
      }).format(new Date(v))
    : 'Not yet processed';
