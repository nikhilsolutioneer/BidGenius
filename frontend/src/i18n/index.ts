import { useSyncExternalStore } from 'react';
import german from './de.json' with { type: 'json' };

export type Language = 'en' | 'de';
const storageKey = 'bidgenius_language';
function savedLanguage(): Language {
  try { return localStorage.getItem(storageKey) === 'de' ? 'de' : 'en'; } catch { return 'en'; }
}
let language: Language = savedLanguage();
const listeners = new Set<() => void>();
export const getLanguage = () => language;
export const getLocale = () => language === 'de' ? 'de-CH' : 'en-CH';
export function setLanguage(next: Language) {
  if (next !== 'en' && next !== 'de') return;
  language = next;
  try { localStorage.setItem(storageKey, next); } catch { /* Selection still works for this session. */ }
  if (typeof document !== 'undefined') document.documentElement.lang = next;
  listeners.forEach(listener => listener());
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function useLanguage() { return useSyncExternalStore(subscribe, getLanguage, () => 'en' as Language); }
if (typeof document !== 'undefined') document.documentElement.lang = language;
if (typeof window !== 'undefined') window.addEventListener('storage', event => {
  if (event.key === storageKey || event.key === null) {
    language = savedLanguage();
    document.documentElement.lang = language;
    listeners.forEach(listener => listener());
  }
});

const normalize = (text: string) => text.replace(/\s+/g, ' ').trim();
const entries = Object.entries(german) as [string, string][];
const exact = new Map(entries.map(([english, translation]) => [normalize(english), translation]));
const folded = new Map(entries.map(([english, translation]) => [normalize(english).toLowerCase(), translation]));
for (const [english, translation] of entries) {
  if (english !== english.toUpperCase()) folded.set(normalize(english).toLowerCase(), translation);
}
const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const patterns = entries.filter(([english]) => /\{\d+\}/.test(english)).map(([english, translation]) => ({
  expression: new RegExp('^' + english.split(/\{\d+\}/).map(escape).join('(.+?)') + '$', 'i'),
  translation,
}));

/** Translate known UI messages only. Unknown document/customer text stays intact. */
export function translate(value: string, depth = 0): string {
  if (language === 'en' || !value.trim() || depth > 3) return value;
  const key = normalize(value);
  let translated = exact.get(key) ?? folded.get(key.toLowerCase());
  if (translated === undefined) {
    for (const pattern of patterns) {
      const match = key.match(pattern.expression);
      if (match) {
        translated = pattern.translation.replace(/\{(\d+)\}/g, (_, index: string) => translate(match[Number(index) + 1] || '', depth + 1));
        break;
      }
    }
  }
  if (translated === undefined) return value;
  return `${value.match(/^\s*/)?.[0] || ''}${translated}${value.match(/\s*$/)?.[0] || ''}`;
}
