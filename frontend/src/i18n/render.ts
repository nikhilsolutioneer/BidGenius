import { translate } from './index';

// Translation happens while React constructs the rendered element, never by
// changing DOM nodes behind React. Component props and domain values stay raw.
const textAttributes = ['title', 'placeholder', 'alt', 'aria-label', 'aria-description', 'aria-valuetext'];
const preserveContent = new Set(['pre', 'code', 'textarea', 'script', 'style']);
function textChildren(value: unknown): unknown {
  return typeof value === 'string' ? translate(value) : Array.isArray(value) ? value.map(textChildren) : value;
}
export function localizedProps(type: unknown, incoming: unknown) {
  if (typeof type !== 'string' || !incoming || typeof incoming !== 'object') return incoming;
  const props = { ...incoming } as Record<string, unknown>;
  if (props.translate === 'no') return incoming;
  for (const attribute of textAttributes) {
    if (typeof props[attribute] === 'string') props[attribute] = translate(props[attribute] as string);
  }
  // An option's implicit HTML value must remain the original domain value.
  if (type === 'option' && props.value === undefined && typeof props.children === 'string') props.value = props.children;
  if (!preserveContent.has(type)) props.children = textChildren(props.children);
  return props;
}
