// Reemplazar todos los estudiantes con el Excel de secretaría (solo admin).
// Paso 1: se elige el archivo y el servidor muestra una vista previa sin guardar nada.
// Paso 2: se escribe la confirmación y se reemplaza (con respaldo y conservando correos).
import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, output, signal } from '@angular/core';
import { FileSpreadsheet, LucideAngularModule, Upload } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorMessage } from '../core/http';

interface VistaPrevia {
  validos: number;
  con_error: number;
  errores: string[];
  cedulas_repetidas: string[];
  cursos: number;
  actuales: number;
  nuevos: number;
  se_mantienen: number;
  se_eliminan: number;
  correos_conservados: number;
  correos_perdidos: number;
  animadores_sin_alumnos: string[];
  confirmacion: string;
  puede_importar: boolean;
}

interface Resultado extends VistaPrevia {
  message: string;
  insertados: number;
  borrados: number;
  respaldo: string;
}

@Component({
  selector: 'app-importar-estudiantes',
  imports: [LucideAngularModule],
  template: `
    <section
      id="importar-estudiantes"
      class="rounded-xl border-2 border-amber-300 dark:border-amber-700 bg-white dark:bg-gray-800 p-6 space-y-4"
    >
      <div class="flex items-center gap-2 text-amber-700 dark:text-amber-400">
        <lucide-icon [img]="ExcelIcon" [size]="20" />
        <h2 class="text-lg font-bold">Reemplazar estudiantes con el Excel de secretaría</h2>
      </div>

      <ul class="list-disc pl-5 text-sm text-gray-700 dark:text-gray-300 space-y-1">
        <li>
          Use la plantilla de alumnos de secretaría (<code>.xlsx</code>). Se leen las columnas
          <strong>Nombre</strong>, <strong>Primer Apellido</strong>,
          <strong>Segundo Apellido</strong>, <strong>Curso</strong> y
          <strong>Num documento</strong>; el resto (padres, direcciones, etc.) no se guarda.
        </li>
        <li>
          Reemplaza a <strong>todos</strong> los estudiantes por los del Excel. Los que no estén en
          el Excel se eliminan.
        </li>
        <li>
          Se conserva el correo que cada estudiante ya registró, si su cédula sigue en el Excel.
        </li>
        <li>
          No toca participantes, tablas ni animadores. Antes de reemplazar, el servidor guarda un
          respaldo en su carpeta <code>backups</code>.
        </li>
      </ul>

      <label
        class="flex items-center gap-2 w-fit cursor-pointer bg-gray-200 dark:bg-gray-700 dark:text-white px-4 py-2 rounded-lg"
      >
        <lucide-icon [img]="UploadIcon" [size]="16" />
        {{ archivo() ? 'Cambiar archivo' : 'Elegir Excel (.xlsx)' }}
        <input
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          (change)="elegir($event)"
          class="hidden"
        />
      </label>
      @if (archivo(); as f) {
        <p class="text-sm text-gray-600 dark:text-gray-400">Archivo: {{ f.name }}</p>
      }
      @if (analizando()) {
        <p class="text-gray-600 dark:text-gray-400">Analizando el Excel...</p>
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
        <ul class="text-sm text-gray-700 dark:text-gray-300 space-y-1">
          <li>
            Hoy hay <strong>{{ p.actuales }}</strong> estudiantes: siguen
            <strong>{{ p.se_mantienen }}</strong> · nuevos <strong>{{ p.nuevos }}</strong> · se
            eliminan <strong>{{ p.se_eliminan }}</strong>.
          </li>
          <li>
            Correos registrados: <strong>{{ p.correos_conservados }}</strong> se conservan
            @if (p.correos_perdidos) {
              ·
              <span class="text-amber-700 dark:text-amber-400"
                ><strong>{{ p.correos_perdidos }}</strong> se pierden (estudiantes que ya no
                están)</span
              >
            }
          </li>
          @if (p.animadores_sin_alumnos.length) {
            <li class="text-amber-700 dark:text-amber-400">
              {{ p.animadores_sin_alumnos.length }} animador(es) quedarían sin alumnos en su curso:
              {{ p.animadores_sin_alumnos.join(', ') }}. Revise su curso en Animadores.
            </li>
          }
        </ul>

        @if (p.cedulas_repetidas.length) {
          <div
            class="rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-300 dark:border-red-700 text-red-800 dark:text-red-200 p-3 text-sm"
          >
            Hay cédulas repetidas en el Excel: {{ p.cedulas_repetidas.join(', ') }}. Corríjalas y
            vuelva a elegir el archivo.
          </div>
        }
        @if (p.errores.length) {
          <details class="text-sm text-gray-700 dark:text-gray-300">
            <summary class="cursor-pointer text-amber-700 dark:text-amber-400">
              {{ p.con_error }} fila(s) con problemas no se importarán (ver detalle)
            </summary>
            <ul class="mt-2 list-disc pl-5 space-y-0.5">
              @for (e of p.errores; track $index) {
                <li>{{ e }}</li>
              }
              @if (p.con_error > p.errores.length) {
                <li>… y {{ p.con_error - p.errores.length }} más</li>
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
            (click)="reemplazar()"
            [disabled]="!confirmado() || importando()"
            class="flex items-center gap-2 bg-amber-600 hover:bg-amber-700 text-white px-4 py-2 rounded-lg font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <lucide-icon [img]="UploadIcon" [size]="16" />
            {{ importando() ? 'Importando...' : 'Reemplazar ' + p.validos + ' estudiantes' }}
          </button>
        }
      }

      @if (resultado(); as res) {
        <div
          class="rounded-lg bg-green-50 dark:bg-green-900/30 border border-green-300 dark:border-green-700 text-green-800 dark:text-green-200 p-3 text-sm"
        >
          {{ res.message }} Registros anteriores reemplazados: {{ res.borrados }} · correos
          conservados: {{ res.correos_conservados }}. Respaldo:
          <code>backups/{{ res.respaldo }}</code>
        </div>
      }
      @if (error()) {
        <p class="text-red-600 text-sm">{{ error() }}</p>
      }
    </section>
  `,
})
export class ImportarEstudiantes {
  private readonly http = inject(HttpClient);
  readonly importado = output<void>();

  protected readonly ExcelIcon = FileSpreadsheet;
  protected readonly UploadIcon = Upload;

  protected readonly archivo = signal<File | null>(null);
  protected readonly previa = signal<VistaPrevia | null>(null);
  protected readonly resultado = signal<Resultado | null>(null);
  protected readonly texto = signal('');
  protected readonly analizando = signal(false);
  protected readonly importando = signal(false);
  protected readonly error = signal('');

  protected readonly confirmado = computed(
    () => !!this.previa()?.puede_importar && this.texto().trim() === this.previa()?.confirmacion,
  );
  protected readonly tarjetas = computed(() => {
    const p = this.previa();
    if (!p) return [];
    return [
      { label: 'estudiantes válidos', valor: p.validos },
      { label: 'cursos', valor: p.cursos },
      { label: 'filas con error', valor: p.con_error },
      { label: 'cédulas repetidas', valor: p.cedulas_repetidas.length },
    ];
  });

  private formData(): FormData {
    const data = new FormData();
    const f = this.archivo();
    if (f) data.append('excel', f, f.name);
    return data;
  }

  protected async elegir(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const f = input.files?.[0] || null;
    input.value = ''; // permite volver a elegir el mismo archivo después de corregirlo
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
          this.http.post<VistaPrevia>('/api/estudiantes/importar/vista-previa', this.formData()),
        ),
      );
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo leer el Excel.'));
    } finally {
      this.analizando.set(false);
    }
  }

  protected async reemplazar(): Promise<void> {
    const p = this.previa();
    if (!p || !this.confirmado()) return;
    if (
      !confirm(
        `Se reemplazarán los ${p.actuales} estudiantes actuales por ${p.validos} del Excel ` +
          `(${p.se_eliminan} se eliminan). ¿Continuar?`,
      )
    )
      return;
    this.importando.set(true);
    this.error.set('');
    try {
      const data = this.formData();
      data.append('confirmacion', this.texto().trim());
      const res = await firstValueFrom(
        this.http.post<Resultado>('/api/estudiantes/importar', data),
      );
      this.resultado.set(res);
      this.previa.set(null);
      this.archivo.set(null);
      this.texto.set('');
      this.importado.emit();
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudieron importar los estudiantes.'));
    } finally {
      this.importando.set(false);
    }
  }
}
