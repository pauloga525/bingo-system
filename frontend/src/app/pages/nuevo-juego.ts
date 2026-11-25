// Nuevo juego desde cero (solo admin): borra tablas, ganadoras, participantes y reservas,
// genera la cantidad de tablas indicada y descarga su PDF. Conserva estudiantes y animadores.
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, output, signal } from '@angular/core';
import { Download, LucideAngularModule, RotateCcw } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorMessage, onlyDigits } from '../core/http';

interface Resumen {
  tablas: number;
  tablas_asignadas: number;
  tablas_ganadoras: number;
  participantes: number;
  cuentas_con_reserva: number;
  estudiantes: number;
  animadores: number;
  maximo: number;
  confirmacion: string;
  pdf_actual: string | null;
}

interface Resultado {
  message: string;
  tablas_generadas: number;
  desde: string;
  hasta: string;
  pdf: string;
  respaldo: string;
}

const CANTIDAD_INICIAL = '11000';

@Component({
  selector: 'app-nuevo-juego',
  imports: [LucideAngularModule],
  template: `
    <section
      class="rounded-xl border-2 border-red-300 dark:border-red-800 bg-white dark:bg-gray-800 p-6 space-y-4"
    >
      <div class="flex items-center gap-2 text-red-700 dark:text-red-400">
        <lucide-icon [img]="ResetIcon" [size]="20" />
        <h2 class="text-lg font-bold">Nuevo juego desde cero</h2>
      </div>

      <ul class="list-disc pl-5 text-sm text-gray-700 dark:text-gray-300 space-y-1">
        <li>
          Borra <strong>todas</strong> las tablas (generadas y asignadas), las tablas ganadoras y
          todos los participantes con sus asignaciones.
        </li>
        <li>Los contadores de ventas de los vendedores vuelven a cero.</li>
        <li>Genera la cantidad de tablas nuevas que indique y descarga su PDF para imprimir.</li>
        <li>
          Se conservan los <strong>estudiantes</strong> y los <strong>animadores</strong> (con sus
          correos y cursos).
        </li>
        <li>Antes de borrar, el servidor guarda un respaldo en su carpeta <code>backups</code>.</li>
        <li>
          No es el botón "Nuevo Juego" del tablero: ese solo reinicia la ronda y no borra nada.
        </li>
      </ul>

      @if (loading()) {
        <p class="text-gray-600 dark:text-gray-400">Cargando...</p>
      } @else if (resumen(); as r) {
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
          @for (c of tarjetas(); track c.label) {
            <div class="rounded-lg bg-gray-100 dark:bg-gray-700 p-3">
              <div class="text-2xl font-bold text-gray-900 dark:text-white">{{ c.valor }}</div>
              <div class="text-xs text-gray-600 dark:text-gray-300">{{ c.label }}</div>
            </div>
          }
        </div>
        <p class="text-xs text-gray-500 dark:text-gray-400">
          Se conservan {{ r.estudiantes }} estudiantes y {{ r.animadores }} animadores.
        </p>

        <div class="grid sm:grid-cols-2 gap-3">
          <label class="block text-sm text-gray-700 dark:text-gray-200">
            ¿Cuántas tablas nuevas desea generar?
            <input
              [value]="cantidad()"
              (input)="setCantidad($event)"
              inputmode="numeric"
              autocomplete="off"
              class="mt-1 w-full border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg px-3 py-2"
            />
            @if (cantidadError()) {
              <span class="text-xs text-red-600">{{ cantidadError() }}</span>
            } @else if (cantidadNum()) {
              <span class="text-xs text-gray-500 dark:text-gray-400">
                Seriales CARD00001 a {{ ultimoSerial() }}
              </span>
            }
          </label>
          <label class="block text-sm text-gray-700 dark:text-gray-200">
            Para confirmar escriba <strong class="font-mono">{{ r.confirmacion }}</strong>
            <input
              [value]="texto()"
              (input)="texto.set($any($event.target).value)"
              autocomplete="off"
              class="mt-1 w-full border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg px-3 py-2 font-mono"
            />
          </label>
        </div>

        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            (click)="empezar()"
            [disabled]="!listo() || trabajando()"
            class="flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <lucide-icon [img]="ResetIcon" [size]="16" />
            {{ trabajando() ? 'Generando tablas...' : 'Empezar juego desde cero' }}
          </button>
          @if (r.pdf_actual) {
            <button
              type="button"
              (click)="descargar()"
              [disabled]="descargando()"
              class="flex items-center gap-2 bg-gray-200 dark:bg-gray-700 dark:text-white px-4 py-2 rounded-lg disabled:opacity-60"
            >
              <lucide-icon [img]="DownloadIcon" [size]="16" />
              {{ descargando() ? 'Descargando...' : 'Descargar PDF de tablas' }}
            </button>
          }
        </div>
      }

      @if (resultado(); as res) {
        <div
          class="rounded-lg bg-green-50 dark:bg-green-900/30 border border-green-300 dark:border-green-700 text-green-800 dark:text-green-200 p-3 text-sm"
        >
          {{ res.message }} Seriales {{ res.desde }} a {{ res.hasta }}. El PDF se descargó; si no lo
          ve, use "Descargar PDF de tablas". Respaldo: <code>backups/{{ res.respaldo }}</code>
        </div>
      }
      @if (error()) {
        <p class="text-red-600 text-sm">{{ error() }}</p>
      }
    </section>
  `,
})
export class NuevoJuego implements OnInit {
  private readonly http = inject(HttpClient);
  /** Avisa al contenedor para que actualice sus contadores. */
  readonly reiniciado = output<void>();

  protected readonly ResetIcon = RotateCcw;
  protected readonly DownloadIcon = Download;

  protected readonly resumen = signal<Resumen | null>(null);
  protected readonly resultado = signal<Resultado | null>(null);
  protected readonly cantidad = signal(CANTIDAD_INICIAL);
  protected readonly texto = signal('');
  protected readonly loading = signal(true);
  protected readonly trabajando = signal(false);
  protected readonly descargando = signal(false);
  protected readonly error = signal('');

  protected readonly cantidadNum = computed(() => parseInt(this.cantidad(), 10) || 0);
  protected readonly cantidadError = computed(() => {
    const max = this.resumen()?.maximo || 0;
    const n = this.cantidadNum();
    if (!this.cantidad()) return 'Indique la cantidad de tablas.';
    if (n <= 0 || (max && n > max)) return `Debe estar entre 1 y ${max}.`;
    return '';
  });
  protected readonly ultimoSerial = computed(
    () => `CARD${String(this.cantidadNum()).padStart(5, '0')}`,
  );
  protected readonly listo = computed(
    () =>
      !!this.resumen() &&
      !this.cantidadError() &&
      this.texto().trim() === this.resumen()?.confirmacion,
  );
  protected readonly tarjetas = computed(() => {
    const r = this.resumen();
    if (!r) return [];
    return [
      { label: 'tablas actuales', valor: r.tablas },
      { label: 'tablas asignadas', valor: r.tablas_asignadas },
      { label: 'participantes', valor: r.participantes },
      { label: 'tablas ganadoras', valor: r.tablas_ganadoras },
    ];
  });

  ngOnInit(): void {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    this.loading.set(true);
    try {
      this.resumen.set(await firstValueFrom(this.http.get<Resumen>('/api/juego/nuevo')));
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo cargar el resumen.'));
    } finally {
      this.loading.set(false);
    }
  }

  protected setCantidad(event: Event): void {
    const el = event.target as HTMLInputElement;
    el.value = onlyDigits(el.value);
    this.cantidad.set(el.value);
  }

  protected async empezar(): Promise<void> {
    const r = this.resumen();
    if (!r || !this.listo()) return;
    const n = this.cantidadNum();
    if (
      !confirm(
        `Se borrarán ${r.tablas} tablas, ${r.participantes} participantes y ${r.tablas_ganadoras} ` +
          `ganadoras, y se generarán ${n} tablas nuevas. Esta acción no se puede deshacer desde el ` +
          'panel. ¿Continuar?',
      )
    )
      return;
    this.trabajando.set(true);
    this.error.set('');
    this.resultado.set(null);
    try {
      const res = await firstValueFrom(
        this.http.post<Resultado>('/api/juego/nuevo', {
          cantidad: n,
          confirmacion: this.texto().trim(),
        }),
      );
      this.resultado.set(res);
      this.texto.set('');
      await this.cargar();
      this.reiniciado.emit();
      await this.descargar();
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo empezar el juego nuevo.'));
    } finally {
      this.trabajando.set(false);
    }
  }

  /** Descarga el PDF de las tablas del último juego (requiere la sesión del admin). */
  protected async descargar(): Promise<void> {
    this.descargando.set(true);
    try {
      const blob = await firstValueFrom(
        this.http.get('/api/juego/tablas.pdf', { responseType: 'blob' }),
      );
      const nombre = this.resumen()?.pdf_actual || 'tablas.pdf';
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `bingo-${nombre}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo descargar el PDF de tablas.'));
    } finally {
      this.descargando.set(false);
    }
  }
}
