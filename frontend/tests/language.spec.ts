import { expect, test } from '@playwright/test';
import { mockWorkspace, savedRun } from './fixtures/mock-workspace';
import { setLanguage, translate } from '../src/i18n';
import { localizedProps } from '../src/i18n/render';

test('German translates navigation, overview, run dialog and estimate while preserving project data', async ({ page }) => {
  const failures: string[] = [];
  page.on('pageerror', error => failures.push(error.message));
  const state = await mockWorkspace(page, savedRun({ extraction_mode: 'local_then_ai', model: 'test-model' }));
  const price = await page.locator('.price-card').innerText();
  await page.getByRole('combobox', { name: 'Interface language' }).selectOption('de');
  await expect(page.locator('html')).toHaveAttribute('lang', 'de');
  await expect(page.getByRole('heading', { name: 'Jede Zahl. Durch Nachweise belegt.' })).toBeVisible();
  const navigation = page.getByRole('navigation', { name: 'Hauptnavigation' });
  await expect(navigation.getByRole('button', { name: 'Kalkulation', exact: true })).toBeVisible();
  await expect(page.locator('.breadcrumb')).toContainText('Mock tender');
  const priceAfter = await page.locator('.price-card').innerText();
  expect(priceAfter.match(/CHF\s*[\d’.,]+/g)).toEqual(price.match(/CHF\s*[\d’.,]+/g));
  await page.getByRole('button', { name: 'Verarbeitungsprotokoll', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: 'Verarbeitungsprotokoll' })).toBeVisible();
  await expect(dialog).toContainText('1. Lokale Extraktion');
  await expect(dialog).toContainText('12 lokal erkannte Positionen');
  await expect(dialog).toContainText('Keine geeigneten ungeklärten Angaben');
  await dialog.getByRole('button', { name: 'Schliessen', exact: true }).click();
  await navigation.getByRole('button', { name: 'Kalkulation', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Prüfen. Entscheiden. Begründen.' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Kalkulation durchsuchen' })).toHaveAttribute('placeholder', 'Positionen, Produkte suchen…');
  await page.screenshot({ path: 'test-artifacts/language-german-estimate.png', fullPage: true });
  await page.getByRole('combobox', { name: 'Sprache der Oberfläche' }).selectOption('en');
  await expect(page.getByRole('heading', { name: 'Inspect. Decide. Defend.' })).toBeVisible();
  expect(state.writes).toEqual([]);
  expect(failures).toEqual([]);
});

test('selected language survives reload and remains usable on a narrow screen', async ({ page }) => {
  await mockWorkspace(page);
  await page.getByRole('combobox', { name: 'Interface language' }).selectOption('de');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', 'de');
  await expect(page.getByRole('heading', { name: 'Ihre Projekte' })).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'Sprache der Oberfläche' })).toHaveValue('de');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('combobox', { name: 'Sprache der Oberfläche' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
  expect(await page.locator('.header-right').evaluate(element => element.getBoundingClientRect().right <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: 'test-artifacts/language-german-mobile.png', fullPage: true });
  await page.getByRole('combobox', { name: 'Sprache der Oberfläche' }).selectOption('en');
  await expect(page.getByRole('heading', { name: 'Your projects' })).toBeVisible();
});

test('changing language preserves unsaved login input and original role value', async ({ page }) => {
  await mockWorkspace(page);
  await page.addInitScript(() => localStorage.removeItem('bidgenius_session'));
  await page.reload();
  await page.getByRole('textbox', { name: 'Estimator name' }).fill('Anja Muster');
  await page.getByRole('combobox', { name: 'Interface language' }).selectOption('de');
  await expect(page.getByRole('heading', { name: 'Arbeitsbereich öffnen' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Name des Kalkulators' })).toHaveValue('Anja Muster');
  await page.getByRole('button', { name: 'Arbeitsbereich öffnen' }).click();
  await expect(page.getByRole('heading', { name: 'Ihre Projekte' })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('bidgenius_role'))).toBe('Estimator');
  expect(await page.evaluate(() => localStorage.getItem('bidgenius_actor'))).toBe('Anja Muster');
});

test('translation preserves option values, source text and interpolation', () => {
  setLanguage('de');
  try {
    expect(translate('12 positions found locally')).toBe('12 lokal erkannte Positionen');
    expect(translate('Started')).toBe('Gestartet');
    expect(translate('Kanal DN 100, Originaltext 2.50 m')).toBe('Kanal DN 100, Originaltext 2.50 m');
    expect(localizedProps('option', { children: 'Air terminal' })).toMatchObject({ value: 'Air terminal', children: 'Luftdurchlass' });
    expect(localizedProps('div', { translate: 'no', children: 'Source evidence' })).toMatchObject({ children: 'Source evidence' });
    expect(localizedProps('input', { value: 'Overview', placeholder: 'Search estimate' })).toMatchObject({ value: 'Overview', placeholder: 'Kalkulation durchsuchen' });
  } finally { setLanguage('en'); }
});
