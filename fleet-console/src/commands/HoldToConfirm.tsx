// Confirming a risky command takes a deliberate press: hold the pointer, or Space, for
// HOLD_MS (ADR 0015: no risky command from a single keystroke). Enter does nothing here, and
// releasing early confirms nothing. The fill is a CSS animation of the same length.
import { useEffect, useRef, useState } from 'react';

export const HOLD_MS = 1000;

interface Props {
  label: string;
  onConfirm: () => void;
  disabled?: boolean;
}

export function HoldToConfirm({ label, onConfirm, disabled = false }: Props) {
  const [holding, setHolding] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stop = () => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
    setHolding(false);
  };

  const begin = () => {
    if (disabled || timer.current !== null) return;
    setHolding(true);
    timer.current = setTimeout(() => {
      timer.current = null;
      setHolding(false);
      onConfirm();
    }, HOLD_MS);
  };

  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current);
    },
    [],
  );

  return (
    <button
      type="button"
      className={holding ? 'hold-to-confirm holding' : 'hold-to-confirm'}
      disabled={disabled}
      aria-label={`${label} (hold for one second)`}
      style={{ ['--hold-ms' as string]: `${String(HOLD_MS)}ms` }}
      onPointerDown={begin}
      onPointerUp={stop}
      onPointerLeave={stop}
      onPointerCancel={stop}
      onKeyDown={(e) => {
        if (e.key === 'Enter') e.preventDefault(); // Enter never confirms
        if (e.key === ' ') {
          e.preventDefault();
          if (!e.repeat) begin();
        }
      }}
      onKeyUp={(e) => {
        if (e.key === ' ') stop();
      }}
      onClick={(e) => {
        e.preventDefault(); // a click alone confirms nothing
      }}
    >
      <span className="hold-fill" aria-hidden="true" />
      <span className="hold-label">{label}</span>
    </button>
  );
}
