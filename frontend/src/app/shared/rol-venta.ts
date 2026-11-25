// Selector "Vender como" para vendedores con varios roles. La venta queda a nombre de ese rol
// (las ventas a alumnos con un rol sin curso son venta externa del rol, no del curso).
import { Component, computed, inject, input, model } from '@angular/core';

import { CARGOS, Cargo, SessionService } from '../core/session';

@Component({
  selector: 'app-rol-venta',
  template: `
    @if (opciones().length > 1) {
      <fieldset>
        <legend class="text-lg font-semibold text-yellow-500 mb-2">Vender como</legend>
        <select
          [value]="rol()"
          (change)="rol.set($any($event.target).value)"
          class="p-3 w-full border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
        >
          @for (c of opciones(); track c) {
            <option [value]="c" [selected]="c === rol()">{{ nombre(c) }}</option>
          }
        </select>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">
          La venta se registra con este rol en los reportes.
        </p>
      </fieldset>
    }
  `,
})
export class RolVenta {
  private readonly session = inject(SessionService);
  /** Rol elegido ('' = el que decida el servidor). */
  readonly rol = model<string>('');
  /** Limita los roles mostrados (p. ej. sin 'animador' para alumnos de otro curso). */
  readonly permitidos = input<Cargo[] | null>(null);

  protected readonly opciones = computed(() => {
    const p = this.permitidos();
    return this.session.cargosVenta().filter((c) => !p || p.includes(c));
  });

  protected nombre(c: Cargo): string {
    return c === 'admin' ? 'Administrador' : CARGOS[c];
  }
}
