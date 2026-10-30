// Estado de la bandeja de «Notificaciones»: una página de avisos para un filtro, «cargar más» y marcar como leído.
//
// Marcar como leído es optimista: el aviso cambia al instante y, si el backend lo rechaza, vuelve a como estaba y se informa el error.
// Cada cambio de filtro descarta las respuestas de la anterior (no se mezclan avisos de filtros distintos).

import { useCallback, useEffect, useRef, useState } from 'react';

import * as notificationsApi from '../../../api/notificationsApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';

export const PAGE_SIZE = 20;

const INITIAL = { status: 'loading', items: [], noLeidas: null, hayMas: false, total: 0, loadError: '' };

export function useNotificationList(params) {
  const [state, setState] = useState(INITIAL);
  const [loadingMore, setLoadingMore] = useState(false);
  const [actionError, setActionError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const paramsKey = JSON.stringify(params);
  const latest = useRef(state);
  latest.current = state;
  const generation = useRef(0);
  const pending = useRef(new Set());

  useEffect(() => {
    const mine = ++generation.current;
    setState((current) => ({ ...INITIAL, noLeidas: current.noLeidas }));
    setActionError('');
    notificationsApi.getNotifications({ ...JSON.parse(paramsKey), limite: PAGE_SIZE })
      .then((inbox) => {
        if (generation.current !== mine) return;
        setState({
          status: 'ready', items: inbox.notificaciones, noLeidas: inbox.noLeidas, hayMas: inbox.hayMas, total: inbox.total, loadError: '',
        });
      })
      .catch((error) => {
        if (generation.current !== mine) return;
        setState((current) => ({ ...current, status: 'error', loadError: friendlyError(error) }));
      });
    return () => {
      generation.current += 1;
    };
  }, [paramsKey, reloadKey]);

  const reload = useCallback(() => setReloadKey((key) => key + 1), []);

  const loadMore = useCallback(async () => {
    const mine = generation.current;
    setLoadingMore(true);
    setActionError('');
    try {
      const inbox = await notificationsApi.getNotifications({
        ...JSON.parse(paramsKey), limite: PAGE_SIZE, desplazamiento: latest.current.items.length,
      });
      if (generation.current !== mine) return;
      setState((current) => {
        const known = new Set(current.items.map((item) => item.idNotificacion));
        const fresh = inbox.notificaciones.filter((item) => !known.has(item.idNotificacion));
        return { ...current, items: [...current.items, ...fresh], hayMas: inbox.hayMas, total: inbox.total, noLeidas: inbox.noLeidas };
      });
    } catch (error) {
      if (generation.current === mine) setActionError(friendlyError(error));
    } finally {
      setLoadingMore(false);
    }
  }, [paramsKey]);

  const markRead = useCallback(async (idNotificacion) => {
    const target = latest.current.items.find((item) => item.idNotificacion === idNotificacion);
    if (!target || target.leida || pending.current.has(idNotificacion)) return;
    pending.current.add(idNotificacion);
    const setRead = (leida) => (current) => ({
      ...current,
      items: current.items.map((item) => (item.idNotificacion === idNotificacion ? { ...item, leida } : item)),
      noLeidas: Math.max(0, (current.noLeidas ?? 0) + (leida ? -1 : 1)),
    });
    setState(setRead(true));
    try {
      const result = await notificationsApi.markNotificationRead(idNotificacion);
      setState((current) => ({ ...current, noLeidas: result.noLeidas }));
    } catch (error) {
      setState(setRead(false));
      setActionError(friendlyError(error));
    } finally {
      pending.current.delete(idNotificacion);
    }
  }, []);

  const markAllRead = useCallback(async () => {
    const before = latest.current;
    const unread = new Set(before.items.filter((item) => !item.leida).map((item) => item.idNotificacion));
    setActionError('');
    setState((current) => ({ ...current, noLeidas: 0, items: current.items.map((item) => ({ ...item, leida: true })) }));
    try {
      const result = await notificationsApi.markAllNotificationsRead();
      setState((current) => ({ ...current, noLeidas: result.noLeidas }));
    } catch (error) {
      setState((current) => ({
        ...current,
        noLeidas: before.noLeidas,
        items: current.items.map((item) => (unread.has(item.idNotificacion) ? { ...item, leida: false } : item)),
      }));
      setActionError(friendlyError(error));
    }
  }, []);

  // Quitar de la bandeja (eliminación lógica en el backend): desaparece al instante y, si el backend lo rechaza, vuelve a su lugar. Es independiente de
  // leer: un aviso eliminado deja de contarse como no leído, uno leído sigue contándose como leído hasta eliminarse.
  const deleteOne = useCallback(async (idNotificacion) => {
    const before = latest.current;
    const index = before.items.findIndex((item) => item.idNotificacion === idNotificacion);
    if (index < 0 || pending.current.has(idNotificacion)) return;
    const target = before.items[index];
    pending.current.add(idNotificacion);
    setActionError('');
    setState((current) => ({
      ...current,
      items: current.items.filter((item) => item.idNotificacion !== idNotificacion),
      total: Math.max(0, current.total - 1),
      noLeidas: target.leida ? current.noLeidas : Math.max(0, (current.noLeidas ?? 0) - 1),
    }));
    try {
      const result = await notificationsApi.deleteNotification(idNotificacion);
      setState((current) => ({ ...current, noLeidas: result.noLeidas }));
    } catch (error) {
      setState((current) => {
        const items = [...current.items];
        items.splice(Math.min(index, items.length), 0, target);
        return { ...current, items, total: current.total + 1, noLeidas: target.leida ? current.noLeidas : (current.noLeidas ?? 0) + 1 };
      });
      setActionError(friendlyError(error));
    } finally {
      pending.current.delete(idNotificacion);
    }
  }, []);

  const deleteMany = useCallback(async (alcance) => {
    const before = latest.current;
    setActionError('');
    setState((current) => {
      const items = alcance === 'todas' ? [] : current.items.filter((item) => !item.leida);
      return {
        ...current, items, total: alcance === 'todas' ? 0 : Math.max(0, current.total - (current.items.length - items.length)),
        hayMas: alcance === 'todas' ? false : current.hayMas, noLeidas: alcance === 'todas' ? 0 : current.noLeidas,
      };
    });
    try {
      const result = await notificationsApi.deleteNotifications(alcance);
      setState((current) => ({ ...current, noLeidas: result.noLeidas }));
      // Había más avisos de los cargados: la lista se vuelve a pedir para traer lo que quedó (y el total real).
      if (before.hayMas && alcance === 'leidas') setReloadKey((key) => key + 1);
      return result.eliminadas;
    } catch (error) {
      setState((current) => ({ ...current, items: before.items, total: before.total, hayMas: before.hayMas, noLeidas: before.noLeidas }));
      setActionError(friendlyError(error));
      return null;
    }
  }, []);

  return { ...state, loadingMore, actionError, reload, loadMore, markRead, markAllRead, deleteOne, deleteMany };
}
