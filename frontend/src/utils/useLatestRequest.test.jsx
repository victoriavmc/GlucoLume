import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useLatestRequest } from './useLatestRequest.js';

describe('useLatestRequest', () => {
  it('solo la última consulta iniciada sigue siendo vigente', () => {
    const { result } = renderHook(() => useLatestRequest());
    let first; let second;
    act(() => { first = result.current(); });
    expect(first()).toBe(true);
    act(() => { second = result.current(); });
    expect(first()).toBe(false);
    expect(second()).toBe(true);
  });

  it('al desmontar, ninguna consulta pendiente es vigente', () => {
    const { result, unmount } = renderHook(() => useLatestRequest());
    let pending;
    act(() => { pending = result.current(); });
    unmount();
    expect(pending()).toBe(false);
  });

  it('devuelve siempre la misma función entre renders (se puede usar en dependencias)', () => {
    const { result, rerender } = renderHook(() => useLatestRequest());
    const before = result.current;
    rerender();
    expect(result.current).toBe(before);
  });
});
