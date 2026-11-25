// Primer ingreso de un vendedor: confirma su nombre (tomado de su cuenta de Google) antes de usar el panel.
import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { errorMessage } from '../core/http';
import { SessionService, Usuario } from '../core/session';

@Component({
  selector: 'app-bienvenida',
  template: `
    <div class="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
      <form
        (submit)="confirmar($event)"
        class="bg-white dark:bg-gray-800 rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4"
      >
        <h2 class="text-xl font-bold text-gray-900 dark:text-white">¡Bienvenido al Bingo UETS!</h2>
        <p class="text-sm text-gray-600 dark:text-gray-300">
          Es tu primer ingreso. Confirma cómo aparecerá tu nombre en las ventas y reportes.
        </p>
        <label class="block text-sm text-gray-700 dark:text-gray-200">
          Nombres completos
          <input
            [value]="nombre()"
            (input)="nombre.set($any($event.target).value)"
            required
            class="mt-1 w-full border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg px-3 py-2"
          />
        </label>
        <dl class="text-sm grid grid-cols-3 gap-y-1 text-gray-700 dark:text-gray-300">
          <dt class="font-semibold">Correo</dt>
          <dd class="col-span-2">{{ usuario()?.correo }}</dd>
          <dt class="font-semibold">Rol</dt>
          <dd class="col-span-2">{{ usuario()?.cargo_nombre || 'Animador' }}</dd>
          @if (curso()) {
            <dt class="font-semibold">Curso</dt>
            <dd class="col-span-2">{{ curso() }}</dd>
          }
        </dl>
        @if (error()) {
          <p class="text-sm text-red-600">{{ error() }}</p>
        }
        <button
          type="submit"
          [disabled]="guardando() || !nombre().trim()"
          class="w-full bg-blue-600 hover:bg-blue-700 text-white py-2.5 rounded-lg font-semibold disabled:opacity-50"
        >
          {{ guardando() ? 'Guardando...' : 'Confirmar y entrar' }}
        </button>
      </form>
    </div>
  `,
})
export class Bienvenida {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  protected readonly usuario = this.session.user;
  protected readonly nombre = signal(
    this.session.user()?.nombre_google || this.session.user()?.nombres || '',
  );
  protected readonly guardando = signal(false);
  protected readonly error = signal('');

  protected curso(): string {
    const u = this.usuario();
    return u?.curso
      ? [u.curso, u.especialidad, `${u.nivel}°`, u.paralelo].filter(Boolean).join(' · ')
      : '';
  }

  protected async confirmar(event: Event): Promise<void> {
    event.preventDefault();
    if (this.guardando()) return;
    this.guardando.set(true);
    this.error.set('');
    try {
      const resp = await firstValueFrom(
        this.http.post<{ usuario: Usuario }>('/api/auth/onboarding', { nombre: this.nombre() }),
      );
      this.session.updateUser(resp.usuario);
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo guardar.'));
    } finally {
      this.guardando.set(false);
    }
  }
}
