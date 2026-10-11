import { jsx as reactJsx, jsxs as reactJsxs } from 'react/jsx-runtime';
import { localizedProps } from './render';
export { Fragment } from 'react/jsx-runtime';
export type { JSX } from 'react/jsx-runtime';
export const jsx: typeof reactJsx = (type, props, key) => reactJsx(type, localizedProps(type, props), key);
export const jsxs: typeof reactJsxs = (type, props, key) => reactJsxs(type, localizedProps(type, props), key);
