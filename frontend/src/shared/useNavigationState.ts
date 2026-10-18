import { useCallback, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';

/** Navigation only: never put form values, credentials, or fetched data in the URL. */
export function useNavigationState<T extends string>(
  key: string,
  fallback: T,
  allowed?: readonly T[],
): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => {
    const requested = new URLSearchParams(window.location.search).get(key);
    return requested !== null && (!allowed || allowed.includes(requested as T))
      ? requested as T : fallback;
  });
  const current = useRef(value);
  const setNavigation = useCallback<Dispatch<SetStateAction<T>>>((action) => {
    const next = typeof action === 'function' ? action(current.current) : action;
    current.current = next;
    const url = new URL(window.location.href);
    if (next) url.searchParams.set(key, next);
    else url.searchParams.delete(key);
    // Write in the event/async callback, not a React updater (which can run twice).
    // Initial authentication and rendering must not overwrite the requested URL.
    window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
    setValue(next);
  }, [key]);
  return [value, setNavigation];
}
