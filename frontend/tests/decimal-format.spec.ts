import { test, expect } from '@playwright/test';
import { compareDecimal, humanEvidence, money, number, percentOf, probabilityPercent } from '../src/api';

test('money uses exact decimal strings and half-up display rounding', () => {
  expect(money('1568823.525', 2)).toBe('CHF 1’568’823.53');
  expect(money('-0.005', 2)).toBe('CHF -0.01');
  expect(money('9007199254740993.005', 2)).toBe('CHF 9’007’199’254’740’993.01');
  expect(money(null, 2)).toBe('Unpriced');
  expect(number('4.346875', 6)).toBe('4.346875');
  expect(compareDecimal('9007199254740993.01', '9007199254740993.00')).toBe(1);
  expect(percentOf('112', '679')).toBe('16.5');
  expect(probabilityPercent('0.7525')).toBe('75.3');
  expect(humanEvidence('Catalogue width_mm')).toBe('Catalogue Width (mm)');
  expect(humanEvidence('Function: AHU_LARGE')).toBe('Function: Large air handling unit');
});
