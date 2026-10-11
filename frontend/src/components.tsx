import * as Dialog from '@radix-ui/react-dialog';
import { X, LoaderCircle, AlertTriangle, Check, Circle } from 'lucide-react';
import type { ReactNode, ButtonHTMLAttributes } from 'react';
import { cloneElement, isValidElement, useId, useRef } from 'react';
import type { ReactElement } from 'react';
import { label } from './api';
import { translate } from './i18n';
export function countOrDash(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '–';
  const numeric = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(numeric) ? String(value) : '–';
}
export function Button({
  children,
  variant = 'default',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'default' | 'primary' | 'ghost' | 'danger' }) {
  return (
    <button className={`btn btn-${variant} ${className}`} {...props}>
      {children}
    </button>
  );
}
export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: string }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
export function Status({ status }: { status: string }) {
  const good = ['calculated', 'accepted', 'complete', 'strong'].includes(status);
  const bad = ['conflicting', 'failed', 'blocker', 'incompatible', 'rejected'].includes(status);
  return (
    <Badge
      tone={
        good
          ? 'green'
          : bad
            ? 'red'
            : status === 'non_priceable' || status === 'out_of_scope'
              ? 'neutral'
              : 'amber'
      }
    >
      {good ? <Check size={11} /> : bad ? <AlertTriangle size={11} /> : <Circle size={7} />} {label(status)}
    </Badge>
  );
}
export function Spinner({ text = 'Loading…' }: { text?: string }) {
  return (
    <div className="loading">
      <LoaderCircle size={22} className="spin" />
      <span>{text}</span>
    </div>
  );
}
export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="empty-state">
      {icon}
      <h3>{title}</h3>
      {children && <p>{children}</p>}
    </div>
  );
}
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  wide = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description: string;
  children: ReactNode;
  wide?: boolean;
}) {
  const opener = useRef<HTMLElement | null>(null);
  return (
    <Dialog.Root open={open} onOpenChange={(v) => !v && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content
          className={`modal ${wide ? 'modal-wide' : ''}`}
          onOpenAutoFocus={() => {
            opener.current = document.activeElement as HTMLElement;
          }}
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            opener.current?.focus();
          }}
        >
          <div className="modal-header">
            <div>
              <Dialog.Title>{translate(title)}</Dialog.Title>
              <Dialog.Description>{translate(description)}</Dialog.Description>
            </div>
            <Dialog.Close className="icon-btn" aria-label={translate('Close dialog')}>
              <X size={20} />
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export function Field({
  label: fieldLabel,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  const id = useId();
  const control = isValidElement(children)
    ? cloneElement(children as ReactElement<Record<string, unknown>>, {
        id,
        'aria-labelledby': `${id}-label`,
        ...(hint ? { 'aria-describedby': `${id}-hint` } : {}),
      })
    : children;
  return (
    <label className="field" htmlFor={id}>
      <span id={`${id}-label`}>{fieldLabel}</span>
      {control}
      {hint && <small id={`${id}-hint`}>{hint}</small>}
    </label>
  );
}
export function ErrorBox({ message }: { message: string }) {
  return (
    <div role="alert" className="error-box">
      <AlertTriangle size={17} />
      <span>{message}</span>
    </div>
  );
}
export function DetailRow({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className="detail-row">
      <span>{name}</span>
      <strong>{children}</strong>
    </div>
  );
}
