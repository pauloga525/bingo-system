// Pantalla de carga global: cuenta las peticiones al API en curso y muestra un overlay
// que bloquea la pantalla (evita clics repetidos y deja claro que se está procesando).
import { HttpContext, HttpContextToken } from '@angular/common/http';
import { Injectable, computed, signal } from '@angular/core';

/** Marca una petición para que NO muestre el overlay (consultas en segundo plano). */
export const SIN_CARGA = new HttpContextToken<boolean>(() => false);
/** Texto del overlay para una petición (p. ej. "Validando cuenta..."). */
export const MENSAJE_CARGA = new HttpContextToken<string>(() => '');

export const sinCarga = (): HttpContext => new HttpContext().set(SIN_CARGA, true);
export const conMensaje = (mensaje: string): HttpContext =>
  new HttpContext().set(MENSAJE_CARGA, mensaje);

@Injectable({ providedIn: 'root' })
export class LoadingService {
  private readonly pendientes = signal<string[]>([]);
  /** Solo se muestra si tarda más de un instante (evita parpadeos en respuestas rápidas). */
  private readonly visibleTras = signal(false);
  private timer: ReturnType<typeof setTimeout> | undefined;

  readonly activo = computed(() => this.pendientes().length > 0 && this.visibleTras());
  readonly mensaje = computed(
    () => [...this.pendientes()].reverse().find((m) => m) || 'Procesando...',
  );

  empezar(mensaje = ''): void {
    this.pendientes.update((l) => [...l, mensaje]);
    if (this.pendientes().length === 1) {
      clearTimeout(this.timer);
      this.timer = setTimeout(() => this.visibleTras.set(true), 150);
    }
  }

  terminar(mensaje = ''): void {
    this.pendientes.update((l) => {
      const i = l.lastIndexOf(mensaje);
      return i < 0 ? l.slice(1) : [...l.slice(0, i), ...l.slice(i + 1)];
    });
    if (!this.pendientes().length) {
      clearTimeout(this.timer);
      this.visibleTras.set(false);
    }
  }
}
