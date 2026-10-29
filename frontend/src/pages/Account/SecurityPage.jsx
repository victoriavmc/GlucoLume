// /app/seguridad: funcionalidades de seguridad que existen en el backend.

import { useAuth } from '../../auth/AuthContext.jsx';
import { AccountDeletionSection } from './security/AccountDeletionSection.jsx';
import { MfaSection } from './security/MfaSection.jsx';
import { PasswordSection } from './security/PasswordSection.jsx';

export default function SecurityPage() {
  const { account } = useAuth();
  return (
    <div className="page is-form security-page">
      <header className="page-head">
        <h1>Seguridad</h1>
        <p>Cómo accedés a tu cuenta y cómo la protegemos.</p>
      </header>
      <PasswordSection account={account} />
      <MfaSection account={account} />
      <AccountDeletionSection account={account} />
    </div>
  );
}
