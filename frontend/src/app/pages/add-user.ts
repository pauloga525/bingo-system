// Alta de participante (alumno, docente o externo) con sus tablas.
import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ArrowLeft, Loader, LucideAngularModule, PlusCircle, Save, Search } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorMessage } from '../core/http';
import { SessionService } from '../core/session';
import { calcularTotal, textoPromociones } from '../core/tablas';

type Tipo = 'alumno' | 'docente' | 'externo';

interface Datos {
  nombre: string;
  apellido: string;
  cedula: string;
  celular: string;
  nivelCurso: string;
  paralelo: string;
  grupoAdetitss: string;
}

const VACIO: Datos = {
  nombre: '',
  apellido: '',
  cedula: '',
  celular: '',
  nivelCurso: '',
  paralelo: '',
  grupoAdetitss: '',
};
const INPUT =
  'p-3 w-full border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white';
const LEGEND = 'text-lg font-semibold text-yellow-500 mb-4';
const NIVEL_BACHILLERATO: Record<string, string> = {
  '1': 'Primero de Bachillerato',
  '2': 'Segundo de Bachillerato',
  '3': 'Tercero de Bachillerato',
};

const nivelCursoDe = (curso: string, nivel: unknown): string => {
  if (curso === 'BACHILLERATO') return NIVEL_BACHILLERATO[String(nivel)] || '';
  if (curso === 'Educación General Básica') return `${nivel}° de Básica`;
  return '';
};

@Component({
  selector: 'app-add-user',
  imports: [LucideAngularModule],
  template: `
    <div class="flex-grow flex items-center justify-center py-12 px-4">
      <div
        class="w-full max-w-2xl space-y-8 bg-white dark:bg-gray-900 rounded-lg p-8 border border-gray-200 dark:border-gray-700"
      >
        <button
          type="button"
          (click)="volver()"
          class="flex items-center gap-2 text-gray-500 hover:text-yellow-500"
        >
          <lucide-icon [img]="ArrowLeftIcon" [size]="20" /> Volver
        </button>

        <div class="text-center">
          <h2 class="text-3xl font-bold text-gray-900 dark:text-white">Crear Nuevo Participante</h2>
          <p class="text-sm text-gray-600 dark:text-gray-400 mt-2">
            Complete el formulario para registrar un nuevo jugador.
          </p>
        </div>

        <form (submit)="enviar($event)" class="space-y-6">
          <fieldset>
            <legend [class]="legend">Tipo de Participante</legend>
            @if (soloExternos()) {
              <input value="Externo" readonly [class]="input" />
              <p class="text-sm text-gray-500 dark:text-gray-400 mt-2">
                Su rol ({{ usuario()?.cargo_nombre }}) solo puede vender tablas a externos.
              </p>
            } @else {
              <select [value]="tipo()" (change)="cambiarTipo($event)" [class]="input">
                <option value="alumno">Alumno</option>
                <option value="docente">Docente</option>
                <option value="externo">Externo</option>
              </select>
            }
          </fieldset>

          @if (tipo() === 'alumno') {
            <fieldset>
              <legend [class]="legend">Nombre del Animador</legend>
              <input
                [value]="usuario()?.nombres || ''"
                readonly
                class="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300"
              />
            </fieldset>
          }
          @if (tipo() === 'docente') {
            <fieldset>
              <legend [class]="legend">Número de grupo ADETITSS</legend>
              <input
                type="number"
                [value]="datos().grupoAdetitss"
                (input)="set('grupoAdetitss', $event)"
                placeholder="(Ej. 5)"
                [class]="input"
              />
            </fieldset>
          }

          <fieldset>
            <legend [class]="legend">Datos Personales</legend>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div class="flex gap-2">
                <div class="relative flex-1">
                  <input
                    [value]="datos().cedula"
                    (input)="set('cedula', $event)"
                    placeholder="Cédula (Ej. 0123456789)"
                    [class]="input"
                  />
                  @if (buscando()) {
                    <div
                      class="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2 text-blue-500"
                    >
                      <lucide-icon [img]="LoaderIcon" [size]="20" class="animate-spin" />
                    </div>
                  }
                </div>
                @if (tipo() !== 'externo') {
                  <button
                    type="button"
                    (click)="buscarPersona()"
                    [disabled]="datos().cedula.length < 10"
                    title="Buscar por cédula"
                    class="px-4 py-3 rounded-lg flex items-center justify-center bg-blue-600 hover:bg-blue-700 text-white disabled:bg-gray-300 disabled:text-gray-500 disabled:cursor-not-allowed"
                  >
                    <lucide-icon [img]="SearchIcon" [size]="20" />
                  </button>
                }
              </div>
              <input
                [value]="datos().nombre"
                (input)="set('nombre', $event)"
                placeholder="Nombre (Ej. Sofía)"
                [class]="input"
              />
              <input
                [value]="datos().apellido"
                (input)="set('apellido', $event)"
                placeholder="Apellido (Ej. Rodríguez)"
                [class]="input"
              />
              <input
                type="tel"
                [value]="datos().celular"
                (input)="set('celular', $event)"
                placeholder="Número de Celular (Ej. 0987654321)"
                [class]="input"
              />
            </div>
          </fieldset>

          @if (tipo() === 'alumno') {
            <fieldset>
              <legend [class]="legend">Información Académica</legend>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <input
                  [value]="datos().nivelCurso"
                  readonly
                  placeholder="Nivel del Curso (se llena al buscar la cédula)"
                  [class]="input"
                />
                <input [value]="datos().paralelo" readonly placeholder="Paralelo" [class]="input" />
              </div>
            </fieldset>
          }

          <fieldset>
            <legend [class]="legend">Tablas de Bingo</legend>
            <p class="text-sm text-gray-600 dark:text-gray-400 mb-3">
              Las tablas se entregan en orden: al guardar se asignan las siguientes disponibles de
              la cola.
            </p>
            <div class="flex flex-wrap items-center gap-3">
              <label class="text-gray-700 dark:text-gray-300" for="cantidad">Cantidad</label>
              <input
                id="cantidad"
                type="number"
                min="1"
                [value]="cantidad()"
                (input)="setCantidad($event)"
                class="w-28 p-3 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
              />
              @for (n of rapidas; track n) {
                <button
                  type="button"
                  (click)="cantidad.set(n); verCola()"
                  class="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-sm dark:text-white hover:bg-gray-100 dark:hover:bg-gray-800"
                >
                  {{ n }}
                </button>
              }
            </div>
            @if (vistaPrevia(); as v) {
              <p class="text-sm text-gray-600 dark:text-gray-400 mt-3">
                Recibiría ahora: <strong>{{ v }}</strong> (si nadie vende antes de guardar).
              </p>
            }
            @if (errorCola()) {
              <p class="text-sm text-red-600 mt-3">{{ errorCola() }}</p>
            }
          </fieldset>

          <fieldset>
            <legend [class]="legend">Resumen de Pago</legend>
            <p class="text-gray-700 dark:text-gray-300 text-lg">
              Total a pagar: <span class="font-bold text-green-600">\${{ totalPagar() }}</span>
            </p>
            @if (promociones()) {
              <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ promociones() }}</p>
            }
          </fieldset>

          <button
            type="submit"
            [disabled]="guardando()"
            class="w-full bg-blue-600 text-white py-3 rounded-lg font-medium flex items-center justify-center gap-2 hover:bg-blue-700 disabled:opacity-60"
          >
            <lucide-icon [img]="SaveIcon" [size]="20" />
            {{ guardando() ? 'Guardando...' : 'Crear Participante' }}
          </button>
        </form>
      </div>
    </div>
  `,
})
export class AddUser {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly session = inject(SessionService);
  protected readonly ArrowLeftIcon = ArrowLeft;
  protected readonly LoaderIcon = Loader;
  protected readonly PlusCircleIcon = PlusCircle;
  protected readonly SaveIcon = Save;
  protected readonly SearchIcon = Search;
  protected readonly input = INPUT;
  protected readonly legend = LEGEND;

  protected readonly usuario = this.session.user;

  /** Secretaría, financiero, parroquia y oratorio solo venden a externos. */
  protected readonly soloExternos = this.session.soloExternos;
  protected readonly tipo = signal<Tipo>(this.session.soloExternos() ? 'externo' : 'alumno');
  protected readonly datos = signal<Datos>({ ...VACIO });
  /** Cantidad de tablas que se venden (se toman de la cola al guardar). */
  protected readonly cantidad = signal(1);
  protected readonly rapidas = [1, 2, 5, 10];
  protected readonly vistaPrevia = signal('');
  protected readonly errorCola = signal('');
  protected readonly buscando = signal(false);
  protected readonly guardando = signal(false);

  protected readonly totalPagar = computed(() => calcularTotal(this.cantidad()));
  protected readonly promociones = computed(() => textoPromociones(this.cantidad()));

  constructor() {
    void this.verCola();
  }

  protected setCantidad(event: Event): void {
    this.cantidad.set(
      Math.max(0, Math.floor(Number((event.target as HTMLInputElement).value) || 0)),
    );
    void this.verCola();
  }

  /** Vista previa de las tablas que tocarían ahora (no las aparta). */
  protected async verCola(): Promise<void> {
    const n = this.cantidad();
    this.vistaPrevia.set('');
    this.errorCola.set('');
    if (n <= 0) return;
    try {
      const resp = await firstValueFrom(
        this.http.post<{ tablas_consecutivas?: string[] }>('/api/obtenerTablasConsecutivas', {
          cantidad_tablas: n,
        }),
      );
      if (n !== this.cantidad()) return; // cambió mientras respondía
      const t = resp.tablas_consecutivas || [];
      this.vistaPrevia.set(t.length > 1 ? `${t[0]} … ${t[t.length - 1]}` : t[0] || '');
    } catch (err) {
      this.errorCola.set(errorMessage(err, 'No se pudo consultar la cola de tablas.'));
    }
  }

  protected volver(): void {
    void this.router.navigateByUrl('/admin/users');
  }

  protected set(campo: keyof Datos, event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.datos.update((d) => ({ ...d, [campo]: value }));
  }

  /** Al cambiar el tipo se reinicia todo el formulario. */
  protected cambiarTipo(event: Event): void {
    this.tipo.set((event.target as HTMLSelectElement).value as Tipo);
    this.datos.set({ ...VACIO });
  }

  protected async buscarPersona(): Promise<void> {
    const cedula = this.datos().cedula.trim();
    if (cedula.length < 10) return;
    const docente = this.tipo() === 'docente';
    this.buscando.set(true);
    try {
      if (docente) {
        const resp = await firstValueFrom(
          this.http.get<{ success: boolean; docente?: Record<string, string> }>(
            `/api/docente/${cedula}`,
          ),
        );
        const d = resp.docente;
        if (resp.success && d) {
          this.datos.update((v) => ({
            ...v,
            nombre: d['Nombre'],
            apellido: d['Apellidos'],
            cedula: d['Cedula'] || cedula,
          }));
        }
      } else {
        const resp = await firstValueFrom(
          this.http.get<{ success: boolean; estudiante?: Record<string, string> }>(
            `/api/estudiante/${cedula}`,
          ),
        );
        const e = resp.estudiante;
        if (resp.success && e) {
          this.datos.update((v) => ({
            ...v,
            nombre: e['Nombre'],
            apellido: `${e['Primer Apellido'] || ''} ${e['Segundo Apellido'] || ''}`.trim(),
            nivelCurso: nivelCursoDe(e['Curso'], e['Nivel']),
            paralelo: e['Paralelo'] || '',
            cedula: e['Num documento'] || cedula,
          }));
        }
      }
    } catch (err) {
      const status = (err as { status?: number }).status;
      alert(
        status === 404
          ? `No se encontró ningún ${docente ? 'docente' : 'estudiante'} con esta cédula`
          : 'Error al conectar con el servidor. Por favor, intente nuevamente',
      );
    } finally {
      this.buscando.set(false);
    }
  }

  protected async enviar(event: Event): Promise<void> {
    event.preventDefault();
    const cantidad = this.cantidad();
    if (cantidad <= 0) {
      alert('Indique cuántas tablas vende');
      return;
    }
    const user = this.usuario();
    const d = this.datos();
    const tipo = this.tipo();
    this.guardando.set(true);
    try {
      const resp = await firstValueFrom(
        this.http.post<{
          success: boolean;
          message?: string;
          participante?: { seriales?: string[]; total_pagar?: number };
        }>('/api/CreateParticipantes', {
          nombre: d.nombre,
          apellido: d.apellido,
          cedula: d.cedula,
          celular: d.celular,
          tipo,
          nivelCurso: tipo === 'alumno' ? d.nivelCurso : '',
          paralelo: tipo === 'alumno' ? d.paralelo : '',
          animador: user?.nombres,
          grupoAdetitss: d.grupoAdetitss,
          cantidad_tablas: cantidad,
          registrado_por: user?.id,
        }),
      );
      if (resp.success) {
        const seriales = resp.participante?.seriales || [];
        alert(
          `Participante creado. Tablas asignadas (${seriales.length}): ${seriales.join(', ')}\n` +
            `Total a pagar: $${resp.participante?.total_pagar ?? this.totalPagar()}`,
        );
        this.volver();
      } else {
        alert(resp.message || 'Error al crear el participante');
      }
    } catch (err) {
      alert(errorMessage(err, 'Error al crear el participante. Por favor, intente nuevamente.'));
    } finally {
      this.guardando.set(false);
    }
  }
}
