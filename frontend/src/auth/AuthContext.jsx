// Estado de sesión de la aplicación.
//
// status: 'loading' (recuperando la sesión al abrir), 'authenticated' o 'anonymous'.
// Al abrir la app, si hay refresh token guardado, se renueva la sesión y se carga /auth/me.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import * as authApi from '../api/authApi.js';
import { onSessionExpired } from '../api/client.js';
import { goToApp, isOnLoginOrigin } from './originGuard.js';
import { clearTokens, getRefreshToken, saveTokens } from './tokenStore.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [status, setStatus] = useState(() => (getRefreshToken() ? 'loading' : 'anonymous'));
  const [account, setAccount] = useState(null);
  // Aviso de una sola pantalla ({ message, path }): sobrevive a las redirecciones del login y se descarta al
  // navegar a otra ruta (lo limpia AuthenticatedLayout).
  const [flash, setFlash] = useState(null);

  const loadAccount = useCallback(async () => {
    const data = await authApi.getAccount();
    setAccount(data);
    setStatus('authenticated');
    return data;
  }, []);

  // Si el refresh token deja de ser válido mientras se usa la app, la sesión local se cierra y las rutas
  // protegidas redirigen al login.
  useEffect(() => {
    onSessionExpired(() => {
      setAccount(null);
      setStatus('anonymous');
    });
    return () => onSessionExpired(null);
  }, []);

  useEffect(() => {
    if (status !== 'loading') return;
    let active = true;
    authApi
      .getAccount()
      .then((data) => {
        if (!active) return;
        setAccount(data);
        setStatus('authenticated');
      })
      .catch(() => {
        if (!active) return;
        clearTokens();
        setStatus('anonymous');
      });
    return () => {
      active = false;
    };
    // Solo al montar: la recuperación inicial de la sesión.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * Procesa un LoginResponse del backend. Con MFA devuelve { mfaRequired, challengeToken } y no abre sesión.
   */
  const handleLoginResponse = useCallback(
    async (response, remember) => {
      if (response.estado === 'MFA_REQUERIDO') {
        return { mfaRequired: true, challengeToken: response.challengeToken };
      }
      if (isOnLoginOrigin()) {
        // Login hecho en localhost: la sesión no se queda aquí. Se pide un código de un solo uso, se cierra esta sesión
        // (el refresh token nunca llega a guardarse) y la aplicación en su propio origen abre una sesión nueva.
        saveTokens(response.tokens, false);
        try {
          const { code } = await authApi.sessionTransfer();
          await authApi.logout().catch(() => {});
          goToApp(code, remember);
        } finally {
          clearTokens();
        }
        return { mfaRequired: false, transferring: true };
      }
      saveTokens(response.tokens, remember);
      const loaded = await loadAccount();
      return { mfaRequired: false, account: loaded };
    },
    [loadAccount],
  );

  const login = useCallback(
    async (identificador, password, remember) =>
      handleLoginResponse(await authApi.login(identificador, password), remember),
    [handleLoginResponse],
  );

  const completeMfa = useCallback(
    async (challengeToken, factor, remember) =>
      handleLoginResponse(await authApi.verifyMfa(challengeToken, factor), remember),
    [handleLoginResponse],
  );

  const completeMfaRecovery = useCallback(
    async (recoveryToken, codigo, remember) =>
      handleLoginResponse(await authApi.verifyMfaRecovery(recoveryToken, codigo), remember),
    [handleLoginResponse],
  );

  /** Activación de una cuenta invitada: la persona eligió sus credenciales y el backend abre la sesión. */
  const completeActivation = useCallback(
    async (token, usuario, password, aceptaPolitica) =>
      handleLoginResponse(await authApi.completeAccountActivation(token, usuario, password, aceptaPolitica), false),
    [handleLoginResponse],
  );

  /** Abre la sesión con un LoginResponse ya obtenido por un flujo propio (p. ej. activar una cuenta administrativa). */
  const acceptLogin = useCallback(async (response, remember = false) => handleLoginResponse(response, remember), [handleLoginResponse]);

  const completeGoogle = useCallback(
    async (code, remember) => handleLoginResponse(await authApi.exchangeGoogleCode(code), remember),
    [handleLoginResponse],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Aunque el servidor no responda, la sesión local se cierra igual.
    } finally {
      clearTokens();
      setAccount(null);
      setStatus('anonymous');
    }
  }, []);

  /** Recarga /auth/me (p. ej. después de activar MFA o crear una contraseña). */
  const refreshAccount = useCallback(() => loadAccount(), [loadAccount]);

  /** Reemplaza la cuenta con un AccountResponse devuelto por el backend (p. ej. al editar el perfil). */
  const updateAccount = useCallback((data) => {
    const { actualizado, detail, ...summary } = data;
    setAccount(summary);
  }, []);

  /** Cierra la sesión solo localmente (la cuenta fue eliminada: el backend ya revocó las sesiones). */
  const clearSession = useCallback(() => {
    clearTokens();
    setAccount(null);
    setStatus('anonymous');
  }, []);

  const value = useMemo(
    () => ({
      status, account, login, completeMfa, completeMfaRecovery, completeGoogle, completeActivation, acceptLogin, logout, refreshAccount, updateAccount,
      clearSession, flash, setFlash,
    }),
    [status, account, login, completeMfa, completeMfaRecovery, completeGoogle, completeActivation, acceptLogin, logout, refreshAccount, updateAccount,
      clearSession, flash],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth debe usarse dentro de <AuthProvider>.');
  return context;
}
