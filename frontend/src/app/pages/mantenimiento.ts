// Mantenimiento (solo admin): reemplazar estudiantes con Excel, nuevo juego desde cero y
// vaciar todos los participantes.
// Muestra antes lo que se borrará y exige escribir el texto de confirmación.
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { AlertTriangle, LucideAngularModule, Trash2 } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorMessage } from '../core/http';
import { ImportarEstudiantes } from './importar-estudiantes';
import { NuevoJuego } from './nuevo-juego';

interface Resumen {
  participantes: number;
  por_tipo: Record<string, number>;
  tablas_asignadas: number;
  vendedores: number;
  confirmacion: string;
}

interface Resultado {
  message: string;
  participantes_borrados: number;
  tablas_liberadas: number;
  respaldo: string | null;
}

@Component({
  selector: 'app-mantenimiento',
  imports: [LucideAngularModule, ImportarEstudiantes, NuevoJuego],
  template: `
    <div class="p-6 max-w-3xl mx-auto space-y-6">
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Mantenimiento</h1>

      <app-importar-estudiantes />

      <app-nuevo-juego (reiniciado)="recargar()" />

      <section
        class="rounded-xl border-2 border-red-300 dark:border-red-800 bg-white dark:bg-gray-800 p-6 space-y-4"
      >
        <div class="flex items-center gap-2 text-red-700 dark:text-red-400">
          <lucide-icon [img]="AlertIcon" [size]="20" />
          <h2 class="text-lg font-bold">Vaciar todos los participantes</h2>
        </div>

        <ul class="list-disc pl-5 text-sm text-gray-700 dark:text-gray-300 space-y-1">
          <li>
            Borra de la base de datos <strong>todos</strong> los participantes (alumnos, docentes y
            externos) de todos los animadores.
          </li>
          <li>Sus tablas quedan libres para volver a venderse.</li>
          <li>Los contadores de ventas de cada animador vuelven a cero.</li>
          <li>
            Se conservan: las reservas de tablas de los animadores, los estudiantes, los animadores
            y el historial de tablas ganadoras.
          </li>
          <li>
            Antes de borrar, el servidor guarda un respaldo en la carpeta
            <code>backups</code> del servidor.
          </li>
        </ul>

        @if (loading()) {
          <p class="text-gray-600 dark:text-gray-400">Cargando...</p>
        } @else if (resumen(); as r) {
          <div class="grid grid-cols-3 gap-3 text-center">
            <div class="rounded-lg bg-gray-100 dark:bg-gray-700 p-3">
              <div class="text-2xl font-bold text-gray-900 dark:text-white">
                {{ r.participantes }}
              </div>
              <div class="text-xs text-gray-600 dark:text-gray-300">participantes</div>
            </div>
            <div class="rounded-lg bg-gray-100 dark:bg-gray-700 p-3">
              <div class="text-2xl font-bold text-gray-900 dark:text-white">
                {{ r.tablas_asignadas }}
              </div>
              <div class="text-xs text-gray-600 dark:text-gray-300">tablas asignadas</div>
            </div>
            <div class="rounded-lg bg-gray-100 dark:bg-gray-700 p-3">
              <div class="text-2xl font-bold text-gray-900 dark:text-white">{{ r.vendedores }}</div>
              <div class="text-xs text-gray-600 dark:text-gray-300">vendedores</div>
            </div>
          </div>
          @if (tipos().length) {
            <p class="text-xs text-gray-500 dark:text-gray-400">
              Por tipo:
              @for (t of tipos(); track t[0]; let last = $last) {
                {{ t[0] }}: {{ t[1] }}{{ last ? '' : ' · ' }}
              }
            </p>
          }

          @if (r.participantes > 0) {
            <label class="block text-sm text-gray-700 dark:text-gray-200">
              Para confirmar escriba <strong class="font-mono">{{ r.confirmacion }}</strong>
              <input
                [value]="texto()"
                (input)="texto.set($any($event.target).value)"
                autocomplete="off"
                class="mt-1 w-full border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg px-3 py-2 font-mono"
              />
            </label>
            <button
              type="button"
              (click)="vaciar()"
              [disabled]="!confirmado() || borrando()"
              class="flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <lucide-icon [img]="TrashIcon" [size]="16" />
              {{ borrando() ? 'Borrando...' : 'Borrar todos los participantes' }}
            </button>
          } @else if (!resultado()) {
            <p class="text-sm text-gray-600 dark:text-gray-400">
              No hay participantes registrados.
            </p>
          }
        }

        @if (resultado(); as res) {
          <div
            class="rounded-lg bg-green-50 dark:bg-green-900/30 border border-green-300 dark:border-green-700 text-green-800 dark:text-green-200 p-3 text-sm"
          >
            {{ res.message }} Tablas liberadas: {{ res.tablas_liberadas }}.
            @if (res.respaldo) {
              Respaldo: <code>backups/{{ res.respaldo }}</code>
            }
          </div>
        }
        @if (error()) {
          <p class="text-red-600 text-sm">{{ error() }}</p>
        }
      </section>
    </div>
  `,
})
export class Mantenimiento implements OnInit {
  private readonly http = inject(HttpClient);
  protected readonly AlertIcon = AlertTriangle;
  protected readonly TrashIcon = Trash2;

  protected readonly resumen = signal<Resumen | null>(null);
  protected readonly resultado = signal<Resultado | null>(null);
  protected readonly texto = signal('');
  protected readonly loading = signal(true);
  protected readonly borrando = signal(false);
  protected readonly error = signal('');

  protected readonly confirmado = computed(
    () => !!this.resumen() && this.texto().trim() === this.resumen()?.confirmacion,
  );
  protected readonly tipos = computed(() => Object.entries(this.resumen()?.por_tipo || {}));

  ngOnInit(): void {
    void this.cargar();
  }

  /** Tras un juego nuevo los participantes ya no existen: se actualiza el resumen. */
  protected recargar(): void {
    this.resultado.set(null);
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    this.loading.set(true);
    try {
      this.resumen.set(await firstValueFrom(this.http.get<Resumen>('/api/participantes/vaciar')));
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo cargar el resumen.'));
    } finally {
      this.loading.set(false);
    }
  }

  protected async vaciar(): Promise<void> {
    const r = this.resumen();
    if (!r || !this.confirmado()) return;
    if (
      !confirm(
        `Se borrarán ${r.participantes} participantes y se liberarán ${r.tablas_asignadas} tablas. ` +
          'Esta acción no se puede deshacer desde el panel. ¿Continuar?',
      )
    )
      return;
    this.borrando.set(true);
    this.error.set('');
    try {
      const res = await firstValueFrom(
        this.http.post<Resultado>('/api/participantes/vaciar', {
          confirmacion: this.texto().trim(),
        }),
      );
      this.resultado.set(res);
      this.texto.set('');
      await this.cargar();
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudieron borrar los participantes.'));
    } finally {
      this.borrando.set(false);
    }
  }
}
