// Cargar la lista oficial de animadores (PDF del DECE o Excel) con vista previa (solo admin).
// Reemplaza correo y curso de los animadores; los que no están en la lista pierden el acceso.
import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { LucideAngularModule, Upload, Users } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorMessage } from '../core/http';

interface VistaPrevia {
  filas: number;
  validas: number;
  nuevos: number;
  actualizados: number;
  sin_cambios: number;
  pierden_acceso: number;
  pierden_acceso_nombres: string[];
  errores: string[];
  con_error: number;
  cursos_sin_animador: number;
  confirmacion: string;
  puede_importar: boolean;
}

interface Resultado extends VistaPrevia {
  message: string;
  respaldo: string;
}

@Component({
  selector: 'app-importar-animadores',
  imports: [LucideAngularModule],
  template: `
    <section
      id="importar-animadores"
      class="rounded-xl border-2 border-blue-300 dark:border-blue-700 bg-white dark:bg-gray-800 p-6 space-y-4"
    >
      <div class="flex items-center gap-2 text-blue-700 dark:text-blue-400">
        <lucide-icon [img]="UsersIcon" [size]="20" />
        <h2 class="text-lg font-bold">Lista oficial de animadores (DECE)</h2>
      </div>
      <ul class="list-disc pl-5 text-sm text-gray-700 dark:text-gray-300 space-y-1">
        <li>
          Suba el <strong>PDF "Docentes animadores de curso"</strong> del DECE o un Excel con las
          columnas Docente, Correo, Nivel, Curso, Especialidad y Paralelo.
        </li>
        <li>
          Cada animador de la lista queda con su <strong>correo</strong> (con él entra con Google) y
          su <strong>curso</strong>. Solo ellos pueden entrar como animadores.
        </li>
        <li>
          Los animadores que <strong>no</strong> estén en la lista pierden el acceso (no se borran
          ni se pierden sus ventas). Secretaría, financiero, parroquia y oratorio no se tocan.
        </li>
        <li>
          Antes de aplicar, el servidor guarda un respaldo en su carpeta <code>backups</code>.
        </li>
      </ul>

      <label
        class="flex items-center gap-2 w-fit cursor-pointer bg-gray-200 dark:bg-gray-700 dark:text-white px-4 py-2 rounded-lg"
      >
        <lucide-icon [img]="UploadIcon" [size]="16" />
        {{ archivo() ? 'Cambiar archivo' : 'Elegir PDF o Excel' }}
        <input
          type="file"
          accept=".pdf,.xlsx,application/pdf"
          (change)="elegir($event)"
          class="hidden"
        />
      </label>
      @if (archivo(); as f) {
        <p class="text-sm text-gray-600 dark:text-gray-400">Archivo: {{ f.name }}</p>
      }
      @if (analizando()) {
        <p class="text-gray-600 dark:text-gray-400">Analizando la lista...</p>
      }

      @if (previa(); as p) {
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
          @for (c of tarjetas(); track c.label) {
            <div class="rounded-lg bg-gray-100 dark:bg-gray-700 p-3">
              <div class="text-2xl font-bold text-gray-900 dark:text-white">{{ c.valor }}</div>
              <div class="text-xs text-gray-600 dark:text-gray-300">{{ c.label }}</div>
            </div>
          }
        </div>
        <p class="text-sm text-gray-700 dark:text-gray-300">
          {{ p.filas }} filas leídas · sin cambios {{ p.sin_cambios }} · cursos sin animador
          {{ p.cursos_sin_animador }}
        </p>
        @if (p.pierden_acceso) {
          <details class="text-sm text-amber-700 dark:text-amber-400">
            <summary class="cursor-pointer">
              {{ p.pierden_acceso }} animador(es) actuales no están en la lista y perderán el acceso
            </summary>
            <p class="mt-1">{{ p.pierden_acceso_nombres.join(', ') }}</p>
          </details>
        }
        @if (p.errores.length) {
          <details class="text-sm text-red-700 dark:text-red-400">
            <summary class="cursor-pointer">{{ p.con_error }} fila(s) con problemas</summary>
            <ul class="mt-2 list-disc pl-5">
              @for (e of p.errores; track $index) {
                <li>{{ e }}</li>
              }
            </ul>
          </details>
        }
        @if (p.puede_importar) {
          <label class="block text-sm text-gray-700 dark:text-gray-200">
            Para confirmar escriba <strong class="font-mono">{{ p.confirmacion }}</strong>
            <input
              [value]="texto()"
              (input)="texto.set($any($event.target).value)"
              autocomplete="off"
              class="mt-1 w-full border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg px-3 py-2 font-mono"
            />
          </label>
          <button
            type="button"
            (click)="aplicar()"
            [disabled]="!confirmado() || aplicando()"
            class="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <lucide-icon [img]="UploadIcon" [size]="16" />
            {{ aplicando() ? 'Aplicando...' : 'Aplicar lista (' + p.validas + ' animadores)' }}
          </button>
        }
      }

      @if (resultado(); as r) {
        <div
          class="rounded-lg bg-green-50 dark:bg-green-900/30 border border-green-300 dark:border-green-700 text-green-800 dark:text-green-200 p-3 text-sm"
        >
          {{ r.message }} Nuevos {{ r.nuevos }} · actualizados {{ r.actualizados }} · sin acceso
          {{ r.pierden_acceso }}. Respaldo: <code>backups/{{ r.respaldo }}</code>
        </div>
      }
      @if (error()) {
        <p class="text-red-600 text-sm">{{ error() }}</p>
      }
    </section>
  `,
})
export class ImportarAnimadores {
  private readonly http = inject(HttpClient);
  protected readonly UsersIcon = Users;
  protected readonly UploadIcon = Upload;

  protected readonly archivo = signal<File | null>(null);
  protected readonly previa = signal<VistaPrevia | null>(null);
  protected readonly resultado = signal<Resultado | null>(null);
  protected readonly texto = signal('');
  protected readonly analizando = signal(false);
  protected readonly aplicando = signal(false);
  protected readonly error = signal('');

  protected readonly confirmado = computed(
    () => !!this.previa()?.puede_importar && this.texto().trim() === this.previa()?.confirmacion,
  );
  protected readonly tarjetas = computed(() => {
    const p = this.previa();
    if (!p) return [];
    return [
      { label: 'animadores válidos', valor: p.validas },
      { label: 'nuevos', valor: p.nuevos },
      { label: 'cambian correo/curso', valor: p.actualizados },
      { label: 'pierden acceso', valor: p.pierden_acceso },
    ];
  });

  private form(): FormData {
    const data = new FormData();
    const f = this.archivo();
    if (f) data.append('archivo', f, f.name);
    return data;
  }

  protected async elegir(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const f = input.files?.[0] || null;
    input.value = '';
    this.archivo.set(f);
    this.previa.set(null);
    this.resultado.set(null);
    this.texto.set('');
    this.error.set('');
    if (!f) return;
    this.analizando.set(true);
    try {
      this.previa.set(
        await firstValueFrom(
          this.http.post<VistaPrevia>('/api/animadores/importar/vista-previa', this.form()),
        ),
      );
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo leer la lista.'));
    } finally {
      this.analizando.set(false);
    }
  }

  protected async aplicar(): Promise<void> {
    const p = this.previa();
    if (!p || !this.confirmado() || this.aplicando()) return;
    if (
      !confirm(
        `Se aplicará la lista: ${p.validas} animadores con acceso y ${p.pierden_acceso} perderán ` +
          'el acceso. ¿Continuar?',
      )
    )
      return;
    this.aplicando.set(true);
    this.error.set('');
    try {
      const data = this.form();
      data.append('confirmacion', this.texto().trim());
      this.resultado.set(
        await firstValueFrom(this.http.post<Resultado>('/api/animadores/importar', data)),
      );
      this.previa.set(null);
      this.archivo.set(null);
      this.texto.set('');
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo aplicar la lista.'));
    } finally {
      this.aplicando.set(false);
    }
  }
}
