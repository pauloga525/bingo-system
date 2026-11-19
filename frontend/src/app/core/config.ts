// Configuración del panel. Se lee de public/env.js (window.__env) para poder
// cambiarla en el servidor sin recompilar; si falta, se usan valores por defecto.

declare global {
  interface Window {
    __env?: Record<string, string | undefined>;
  }
}

const env = (typeof window !== 'undefined' && window.__env) || {};

// Por defecto el API está en el mismo equipo que sirve el panel, puerto 5000.
const defaultApi = () =>
  typeof location !== 'undefined'
    ? `${location.protocol}//${location.hostname}:5000`
    : 'http://localhost:5000';

export const API_BASE_URL = String(env['API_URL'] || defaultApi())
  .trim()
  .replace(/\/+$/, '');

export const GOOGLE_CLIENT_ID = String(
  env['GOOGLE_CLIENT_ID'] ||
    '579049993014-2kgtu0631odv746rvkav01ivglcgihh7.apps.googleusercontent.com',
).trim();
