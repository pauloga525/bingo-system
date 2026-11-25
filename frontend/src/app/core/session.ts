// Sesión del usuario: token firmado por el backend + perfil, guardados en localStorage.
import { Injectable, computed, signal } from '@angular/core';

/** Grupo de permisos: los vendedores (secretaría, financiero, ...) usan los de 'animador'. */
export type Rol = 'admin' | 'animador' | 'estudiante' | 'externo';
export const ROLES: readonly Rol[] = ['admin', 'animador', 'estudiante', 'externo'];

/**
 * Rol del vendedor dentro del panel. Un vendedor puede tener varios.
 * Solo 'animador' tiene curso; los demás venden a externos y a alumnos como venta de su rol.
 */
export type Cargo =
  'admin' | 'animador' | 'secretaria' | 'financiero' | 'parroquia' | 'oratorio' | 'tecniclub';
export const CARGOS: Record<Exclude<Cargo, 'admin'>, string> = {
  animador: 'Animador',
  secretaria: 'Secretaría',
  financiero: 'Financiero',
  parroquia: 'Parroquia',
  oratorio: 'Oratorio',
  tecniclub: 'Tecniclub',
};

export type TipoVenta = 'alumno' | 'docente' | 'externo';

export interface Usuario {
  id: string | null;
  rol: Rol;
  tipo_usuario: number;
  /** Rol principal (el primero de ``cargos``). */
  cargo?: Cargo;
  /** Todos los roles del vendedor. */
  cargos?: Cargo[];
  cargo_nombre?: string;
  cargos_nombres?: Record<string, string>;
  /** true si no tiene el rol animador (no tiene curso). */
  solo_externos?: boolean;
  /** A quién puede vender: alumno, docente (solo animador) y externo. */
  tipos_venta?: TipoVenta[];
  ve_reportes?: boolean;
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
  /** Roles del vendedor (las sesiones antiguas solo traen ``cargo``). */
  readonly cargos = computed<Cargo[]>(() => {
    const u = this._user();
    const c = this.cargo();
    return u?.cargos?.length ? u.cargos : c ? [c] : [];
  });
  /** Roles con los que puede registrar una venta (para elegir "Vender como"). */
  readonly cargosVenta = computed(() => this.cargos().filter((c) => c !== 'admin'));
  readonly tieneCurso = computed(() => this.cargos().includes('animador'));
  readonly soloExternos = computed(() => !!this._user()?.solo_externos);
  readonly tiposVenta = computed<TipoVenta[]>(() => {
    const t = this._user()?.tipos_venta;
    if (t?.length) return t;
    return this.isAdmin() || this.tieneCurso()
      ? ['alumno', 'docente', 'externo']
      : ['alumno', 'externo'];
  });
  /** Reportes: administrador y rol Financiero (el servidor también lo valida). */
  readonly veReportes = computed(
    () => this.isAdmin() || !!this._user()?.ve_reportes || this.cargos().includes('financiero'),
  );

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
