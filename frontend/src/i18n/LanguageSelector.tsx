import { Languages } from 'lucide-react';
import { setLanguage, useLanguage } from './index';
import type { Language } from './index';

export function LanguageSelector() {
  const language = useLanguage();
  return <label className="language-selector">
    <Languages size={16} aria-hidden="true" />
    <select aria-label="Interface language" value={language} onChange={event => setLanguage(event.target.value as Language)}>
      <option value="en" lang="en" translate="no">English</option>
      <option value="de" lang="de" translate="no">Deutsch</option>
    </select>
  </label>;
}
