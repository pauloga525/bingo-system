// Sesión del usuario: token firmado por el backend + perfil, guardados en localStorage.
import { Injectable, computed, signal } from '@angular/core';

/** Grupo de permisos: los vendedores (secretaría, financiero, ...) usan los de 'animador'. */
export type Rol = 'admin' | 'animador' | 'estudiante' | 'externo';
export const ROLES: readonly Rol[] = ['admin', 'animador', 'estudiante', 'externo'];

/** Rol del vendedor dentro del panel. Solo 'animador' tiene curso y vende a alumnos. */
export type Cargo = 'admin' | 'animador' | 'secretaria' | 'financiero' | 'parroquia' | 'oratorio';
export const CARGOS: Record<Exclude<Cargo, 'admin'>, string> = {
  animador: 'Animador',
  secretaria: 'Secretaría',
  financiero: 'Financiero',
  parroquia: 'Parroquia',
  oratorio: 'Oratorio',
};

export interface Usuario {
  id: string | null;
  rol: Rol;
  tipo_usuario: number;
  cargo?: Cargo;
  cargo_nombre?: string;
  /** true para secretaría, financiero, parroquia y oratorio. */
  solo_externos?: boolean;
  /** Primer ingreso de un vendedor: debe confirmar su nombre. */
  onboarding_pendiente?: boolean;
  nombre_google?: string;
  correo?: string;
  usuario?: string;
  nombres?: string;
  cedula?: string;
  curso?: string;
  especialidad?: string;
  nivel?: number | string;
  paralelo?: string;
}

/** Respuesta de /api/auth/google y /api/auth/registro. */
export interface SesionResponse {
  token: string;
  usuario: Usuario;
}

const TOKEN_KEY = 'token';
const USER_KEY = 'usuario';

const readUser = (): Usuario | null => {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null') as Usuario | null;
  } catch {
    return null;
  }
};

/** Ruta de inicio según el rol. */
export const homeFor = (usuario: Usuario | null): string =>
  usuario?.rol === 'estudiante' || usuario?.rol === 'externo' ? '/mis-tablas' : '/admin';

@Injectable({ providedIn: 'root' })
export class SessionService {
  private readonly _user = signal<Usuario | null>(readUser());
  readonly user = this._user.asReadonly();
  readonly role = computed(() => this._user()?.rol ?? null);
  readonly isAdmin = computed(() => this.role() === 'admin');
  /** Rol del vendedor; las sesiones anteriores a los roles nuevos son animadores. */
  readonly cargo = computed<Cargo | null>(() => {
    const u = this._user();
    if (!u || u.rol === 'estudiante' || u.rol === 'externo') return null;
    return u.cargo || (u.rol === 'admin' ? 'admin' : 'animador');
  });
  readonly soloExternos = computed(() => !!this._user()?.solo_externos);
  /** Reportes: administrador y rol Financiero (el servidor también lo valida). */
  readonly veReportes = computed(() => this.isAdmin() || this.cargo() === 'financiero');

  token(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  }

  isLoggedIn(): boolean {
    return !!this.token() && !!this._user();
  }

  save({ token, usuario }: SesionResponse): void {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(usuario));
    this._user.set(usuario);
  }

  /** Actualiza el perfil guardado (p. ej. tras completar el primer ingreso) sin tocar el token. */
  updateUser(usuario: Usuario): void {
    localStorage.setItem(USER_KEY, JSON.stringify(usuario));
    this._user.set(usuario);
  }

  clear(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem('adminLoggedIn');
    this._user.set(null);
    window.google?.accounts?.id?.disableAutoSelect?.();
  }
}
