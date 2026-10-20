import { Link } from 'react-router-dom';

export function LogoMark({ size = 36 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <path d="M16 2c-5 7-10 12.5-10 18a10 10 0 0 0 20 0C26 14.5 21 9 16 2z" fill="#E3101E" />
      <path d="M16 13c-2.4 3.4-4.5 6-4.5 8.5a4.5 4.5 0 0 0 9 0c0-2.5-2.1-5.1-4.5-8.5z" fill="#fff" />
    </svg>
  );
}

export function Logo({ to = '/', label = 'GlucoLume, ir al inicio' }) {
  return (
    <Link to={to} className="logo" aria-label={label}>
      <LogoMark />
      <span className="logo-text">
        Gluco<span>Lume</span>
      </span>
    </Link>
  );
}
