// React reads live state through this hook: at most `hz` renders per second, whatever the
// telemetry rate (ADR 0005). The map does not use it; it redraws per animation frame.
import { useEffect, useLayoutEffect, useRef, useState } from 'react';

import { type LiveState, useLive } from './store';

export const LIST_HZ = 4;

export function useThrottledLive<T>(selector: (state: LiveState) => T, hz = LIST_HZ): T {
  const selectorRef = useRef(selector);
  useLayoutEffect(() => {
    selectorRef.current = selector;
  });
  const [value, setValue] = useState(() => selector(useLive.getState()));

  useEffect(() => {
    const period = 1000 / hz;
    let last = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const flush = () => {
      timer = null;
      last = Date.now();
      setValue(selectorRef.current(useLive.getState()));
    };
    flush(); // catch changes between the first render and subscribing
    const unsubscribe = useLive.subscribe(() => {
      if (timer !== null) return;
      timer = setTimeout(flush, Math.max(0, last + period - Date.now()));
    });
    return () => {
      unsubscribe();
      if (timer !== null) clearTimeout(timer);
    };
  }, [hz]);

  return value;
}
