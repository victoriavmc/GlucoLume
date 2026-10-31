import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { clearQueryCache, invalidateQuery, useCachedQuery } from './queryCache.js';

describe('useCachedQuery', () => {
  it('muestra el dato de la red cuando llega', async () => {
    const loader = vi.fn().mockResolvedValue(['a']);
    const { result } = renderHook(() => useCachedQuery('lista', loader));

    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(result.current.data).toEqual(['a']));
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it('al volver a montar, dibuja lo guardado en el primer render y vuelve a consultar', async () => {
    const first = renderHook(() => useCachedQuery('lista', () => Promise.resolve(['vieja'])));
    await waitFor(() => expect(first.result.current.data).toEqual(['vieja']));
    first.unmount();

    let later = null;
    const loader = vi.fn(() => new Promise(() => {})); // la red tarda: el dato guardado sigue visible
    renderHook(() => { later = useCachedQuery('lista', loader); });
    expect(later.data).toEqual(['vieja']);
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it('invalidateQuery descarta el dato guardado', async () => {
    const { result, unmount } = renderHook(() => useCachedQuery('lista', () => Promise.resolve(['x'])));
    await waitFor(() => expect(result.current.data).toEqual(['x']));
    unmount();

    invalidateQuery('lista');
    const again = renderHook(() => useCachedQuery('lista', () => new Promise(() => {})));
    expect(again.result.current.data).toBeUndefined();
  });

  it('un error expone el error y conserva el dato anterior', async () => {
    const ok = renderHook(() => useCachedQuery('lista', () => Promise.resolve(['ok'])));
    await waitFor(() => expect(ok.result.current.data).toEqual(['ok']));
    ok.unmount();

    const failing = renderHook(() => useCachedQuery('lista', () => Promise.reject(new Error('sin red'))));
    await waitFor(() => expect(failing.result.current.error?.message).toBe('sin red'));
    expect(failing.result.current.data).toEqual(['ok']);
  });

  it('una respuesta vieja no pisa a la de otra clave', async () => {
    let resolveSlow;
    const slow = () => new Promise((resolve) => { resolveSlow = resolve; });
    const { result, rerender } = renderHook(({ key, loader }) => useCachedQuery(key, loader), {
      initialProps: { key: 'pagina:1', loader: slow },
    });
    rerender({ key: 'pagina:2', loader: () => Promise.resolve(['segunda']) });
    await waitFor(() => expect(result.current.data).toEqual(['segunda']));

    await act(async () => resolveSlow(['primera']));
    expect(result.current.data).toEqual(['segunda']);
  });

  it('clearQueryCache vacía todo', async () => {
    const { result, unmount } = renderHook(() => useCachedQuery('lista', () => Promise.resolve([1])));
    await waitFor(() => expect(result.current.data).toEqual([1]));
    unmount();

    clearQueryCache();
    const again = renderHook(() => useCachedQuery('lista', () => new Promise(() => {})));
    expect(again.result.current.data).toBeUndefined();
  });
});
