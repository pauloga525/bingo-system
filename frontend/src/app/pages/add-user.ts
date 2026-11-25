// Alta de participante (alumno, docente o externo) con sus tablas.
// Los roles sin curso (secretaría, financiero, ...) también venden a alumnos: la venta queda
// a nombre de su rol (venta externa, no del curso). Si el alumno ya tiene tablas, se le agregan.
import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ArrowLeft, Loader, LucideAngularModule, PlusCircle, Save, Search } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorBody, errorMessage, isConflict } from '../core/http';
import { conMensaje, sinCarga } from '../core/loading';
import { CARGOS, Cargo, SessionService, TipoVenta } from '../core/session';
import { calcularTotal, textoPromociones } from '../core/tablas';
import { RolVenta } from '../shared/rol-venta';

type Tipo = TipoVenta;

interface Datos {
  nombre: string;
  apellido: string;
  cedula: string;
  correo: string;
  celular: string;
  nivelCurso: string;
  paralelo: string;
  grupoAdetitss: string;
}

/** Venta registrada en el participante (quién vendió, con qué rol y cuántas). */
export interface VentaParticipante {
  vendedor: string;
  vendedor_nombre: string;
  rol: string;
  rol_nombre: string;
  cantidad: number;
  monto: number;
  fecha?: string;
}

/** Participante que ya existe con esa cédula. */
interface Existente {
  _id: string;
  nombre: string;
  apellido: string;
  tipo: string;
  correo: string;
  puede_agregar: boolean;
  ventas: VentaParticipante[];
  tablas: unknown[];
}

const VACIO: Datos = {
  nombre: '',
  apellido: '',
  cedula: '',
  correo: '',
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
const TIPOS: Record<Tipo, string> = { alumno: 'Alumno', docente: 'Docente', externo: 'Externo' };

const nivelCursoDe = (curso: string, nivel: unknown): string => {
  if (curso === 'BACHILLERATO') return NIVEL_BACHILLERATO[String(nivel)] || '';
  if (curso === 'Educación General Básica') return `${nivel}° de Básica`;
  return '';
};

@Component({
  selector: 'app-add-user',
  imports: [LucideAngularModule, RolVenta],
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
            <select [value]="tipo()" (change)="cambiarTipo($event)" [class]="input">
              @for (t of tipos(); track t) {
                <option [value]="t" [selected]="t === tipo()">{{ nombreTipo[t] }}</option>
              }
            </select>
          </fieldset>

          <app-rol-venta [(rol)]="rolVenta" [permitidos]="permitidosRol()" />

          <fieldset>
            <legend [class]="legend">Vendedor</legend>
            <input
              [value]="(usuario()?.nombres || '') + ' · ' + nombreRol(rolEfectivo())"
              readonly
              class="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300"
            />
            @if (tipo() === 'alumno' && rolEfectivo() !== 'animador' && rolEfectivo() !== 'admin') {
              <p class="text-sm text-blue-700 dark:text-blue-300 mt-2">
                Venta externa de {{ nombreRol(rolEfectivo()) }}: cuenta para su rol, no para el
                curso del alumno.
              </p>
            }
          </fieldset>

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
                    (input)="setCedula($event)"
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
                [readonly]="!!existente()"
                placeholder="Nombre (Ej. Sofía)"
                [class]="input"
              />
              <input
                [value]="datos().apellido"
                (input)="set('apellido', $event)"
                [readonly]="!!existente()"
                placeholder="Apellido (Ej. Rodríguez)"
                [class]="input"
              />
              <input
                type="tel"
                [value]="datos().celular"
                (input)="set('celular', $event)"
                [readonly]="!!existente()"
                placeholder="Número de Celular (Ej. 0987654321)"
                [class]="input"
              />
              <div class="md:col-span-2">
                <input
                  type="email"
                  required
                  [value]="datos().correo"
                  (input)="set('correo', $event)"
                  [readonly]="!!existente()"
                  [placeholder]="
                    tipo() === 'alumno'
                      ? 'Correo institucional (nombre.apellido.est@uets.edu.ec)'
                      : 'Correo del comprador (Ej. nombre@gmail.com)'
                  "
                  [class]="input"
                />
                <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  @if (existente()) {
                    Las tablas se envían al correo que ya tiene registrado. Para cambiarlo use
                    "Cambiar correo" en sus cartones.
                  } @else if (tipo() === 'alumno') {
                    Obligatorio. Se carga al buscar la cédula; corríjalo o agréguelo si está mal o
                    falta. Con este correo el estudiante entra al sistema y ve sus tablas.
                  } @else {
                    Obligatorio. Al guardar se le envían sus tablas en PDF a este correo.
                  }
                </p>
              </div>
            </div>
          </fieldset>

          @if (existente(); as e) {
            <div
              class="rounded-lg border p-4 text-sm"
              [class]="
                e.puede_agregar
                  ? 'border-amber-400 bg-amber-50 text-amber-900 dark:bg-amber-900/20 dark:text-amber-200'
                  : 'border-red-400 bg-red-50 text-red-800 dark:bg-red-900/20 dark:text-red-200'
              "
            >
              <p class="font-semibold">
                {{ e.nombre }} {{ e.apellido }} ya está registrado con {{ e.tablas.length }}
                tabla(s).
              </p>
              @for (v of e.ventas; track $index) {
                <p>
                  · {{ v.cantidad }} vendida(s) por {{ v.vendedor_nombre }} ({{ v.rol_nombre }})
                </p>
              }
              @if (e.puede_agregar) {
                <p class="mt-2">Al guardar se le <strong>agregan</strong> las nuevas tablas.</p>
              } @else {
                <p class="mt-2">
                  Solo quien le vendió (o un rol sin curso, si es alumno) puede agregarle tablas.
                </p>
              }
            </div>
          }

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
            @if (existente(); as e) {
              <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
                Ya tiene {{ e.tablas.length }} tabla(s); con estas quedan
                {{ e.tablas.length + cantidad() }} (la promoción cuenta todas).
              </p>
            }
            @if (promociones()) {
              <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ promociones() }}</p>
            }
          </fieldset>

          <button
            type="submit"
            [disabled]="guardando() || (!!existente() && !existente()?.puede_agregar)"
            class="w-full bg-blue-600 text-white py-3 rounded-lg font-medium flex items-center justify-center gap-2 hover:bg-blue-700 disabled:opacity-60"
          >
            <lucide-icon [img]="SaveIcon" [size]="20" />
            {{
              guardando()
                ? 'Guardando...'
                : existente()
                  ? 'Agregar tablas al participante'
                  : 'Crear Participante'
            }}
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
  protected readonly nombreTipo = TIPOS;

  protected readonly usuario = this.session.user;

  /** Tipos que puede vender según sus roles (docente: solo con rol animador). */
  protected readonly tipos = this.session.tiposVenta;
  protected readonly tipo = signal<Tipo>(
    this.session.tieneCurso() || this.session.isAdmin() ? 'alumno' : 'externo',
  );
  /** Rol con que se registra la venta ('' = el que corresponda por defecto). */
  protected readonly rolVenta = signal('');
  protected readonly datos = signal<Datos>({ ...VACIO });
  /** Participante que ya existe con la cédula buscada (se le agregan tablas). */
  protected readonly existente = signal<Existente | null>(null);
  /** Cantidad de tablas que se venden (se toman de la cola al guardar). */
  protected readonly cantidad = signal(1);
  protected readonly rapidas = [1, 2, 5, 10];
  protected readonly vistaPrevia = signal('');
  protected readonly errorCola = signal('');
  protected readonly buscando = signal(false);
  protected readonly guardando = signal(false);

  /** Roles que puede usar en esta venta: docentes solo como animador; alumnos ajenos sin curso. */
  protected readonly permitidosRol = computed<Cargo[] | null>(() => {
    const cargos = this.session.cargosVenta();
    if (this.tipo() === 'docente') return ['animador'];
    const e = this.existente();
    const id = this.usuario()?.id;
    if (e && !e.ventas.some((v) => v.vendedor === id)) {
      return cargos.filter((c) => c !== 'animador');
    }
    return null;
  });

  /** Rol que quedará en la venta (misma regla que el servidor si no se elige). */
  protected readonly rolEfectivo = computed<string>(() => {
    if (this.session.isAdmin()) return 'admin';
    const permitidos = this.permitidosRol();
    const opciones = this.session
      .cargosVenta()
      .filter((c) => !permitidos || permitidos.includes(c));
    const elegido = this.rolVenta();
    if (elegido && (opciones as string[]).includes(elegido)) return elegido;
    if (this.tipo() !== 'externo' && opciones.includes('animador')) return 'animador';
    return opciones[0] || '';
  });

  private readonly yaTiene = computed(() => this.existente()?.tablas.length || 0);
  protected readonly totalPagar = computed(
    () => calcularTotal(this.yaTiene() + this.cantidad()) - calcularTotal(this.yaTiene()),
  );
  protected readonly promociones = computed(() =>
    textoPromociones(this.yaTiene() + this.cantidad()),
  );

  constructor() {
    void this.verCola();
  }

  protected nombreRol(rol: string): string {
    if (rol === 'admin') return 'Administrador';
    return CARGOS[rol as Exclude<Cargo, 'admin'>] || rol;
  }

  protected setCantidad(event: Event): void {
    this.cantidad.set(
      Math.max(0, Math.floor(Number((event.target as HTMLInputElement).value) || 0)),
    );
    void this.verCola();
  }

  /** Vista previa de las tablas que tocarían ahora (no las aparta). Consulta en segundo plano. */
  protected async verCola(): Promise<void> {
    const n = this.cantidad();
    this.vistaPrevia.set('');
    this.errorCola.set('');
    if (n <= 0) return;
    try {
      const resp = await firstValueFrom(
        this.http.post<{ tablas_consecutivas?: string[] }>(
          '/api/obtenerTablasConsecutivas',
          { cantidad_tablas: n },
          { context: sinCarga() },
        ),
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

  /** Cambiar la cédula descarta el participante encontrado antes. */
  protected setCedula(event: Event): void {
    this.set('cedula', event);
    if (this.existente()) {
      this.existente.set(null);
      this.datos.update((d) => ({ ...VACIO, cedula: d.cedula }));
    }
  }

  /** Al cambiar el tipo se reinicia todo el formulario. */
  protected cambiarTipo(event: Event): void {
    this.tipo.set((event.target as HTMLSelectElement).value as Tipo);
    this.datos.set({ ...VACIO });
    this.existente.set(null);
  }

  /** ¿Ya hay un participante con esta cédula? (404 = no). */
  private async buscarExistente(cedula: string): Promise<void> {
    try {
      const resp = await firstValueFrom(
        this.http.get<{ participante?: Existente }>(`/api/participante/cedula/${cedula}`, {
          context: conMensaje('Buscando si ya tiene tablas...'),
        }),
      );
      const e = resp.participante || null;
      this.existente.set(e);
      if (e) {
        this.datos.update((v) => ({
          ...v,
          nombre: e.nombre || v.nombre,
          apellido: e.apellido || v.apellido,
          correo: e.correo || v.correo,
        }));
      }
    } catch {
      this.existente.set(null);
    }
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
            { context: conMensaje('Buscando docente...') },
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
            { context: conMensaje('Buscando estudiante...') },
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
            correo: e['correo'] || '',
          }));
        }
      }
      await this.buscarExistente(cedula);
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

  /** El participante ya tiene tablas: se le agregan (la venta queda a nombre de quien vende). */
  private async agregarAExistente(e: Existente, cantidad: number): Promise<void> {
    const user = this.usuario();
    const resp = await firstValueFrom(
      this.http.post<{ success: boolean; message?: string; seriales?: string[] }>(
        `/api/participante/${e._id}/tablas/${user?.tipo_usuario}`,
        { cantidad, usuario_id: user?.id, rol_venta: this.rolVenta() || undefined },
        { context: conMensaje('Agregando tablas...') },
      ),
    );
    if (!resp.success) {
      alert(resp.message || 'Error al agregar tablas');
      return;
    }
    alert(
      `Tablas agregadas a ${e.nombre} ${e.apellido}: ${(resp.seriales || []).join(', ')}\n` +
        `Cobrar: $${this.totalPagar()}\nSe envía por correo la lista actualizada de tablas.`,
    );
    void this.router.navigate(['/admin/user', e._id, 'cartones']);
  }

  protected async enviar(event: Event): Promise<void> {
    event.preventDefault();
    // Ignora clics o Enter repetidos mientras la venta anterior sigue en curso
    // (mismo efecto que exhaustMap: no se envía una segunda petición).
    if (this.guardando()) return;
    const cantidad = this.cantidad();
    if (cantidad <= 0) {
      alert('Indique cuántas tablas vende');
      return;
    }
    const user = this.usuario();
    const d = this.datos();
    const tipo = this.tipo();
    const existente = this.existente();
    const correo = d.correo.trim().toLowerCase();
    if (!existente && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(correo)) {
      alert('Ingrese un correo válido: ahí se envían las tablas.');
      return;
    }
    if (
      !existente &&
      tipo === 'alumno' &&
      !/(\.est|_?estudiante)@uets\.edu\.ec$|@est\.uets\.edu\.ec$/.test(correo)
    ) {
      alert('El correo del alumno debe ser el institucional (nombre.apellido.est@uets.edu.ec).');
      return;
    }
    this.guardando.set(true);
    try {
      if (existente) {
        await this.agregarAExistente(existente, cantidad);
        return;
      }
      const resp = await firstValueFrom(
        this.http.post<{
          success: boolean;
          message?: string;
          participante?: { seriales?: string[]; total_pagar?: number };
        }>(
          '/api/CreateParticipantes',
          {
            nombre: d.nombre,
            apellido: d.apellido,
            cedula: d.cedula,
            correo,
            celular: d.celular,
            tipo,
            rol_venta: this.rolVenta() || undefined,
            nivelCurso: tipo === 'alumno' ? d.nivelCurso : '',
            paralelo: tipo === 'alumno' ? d.paralelo : '',
            animador: user?.nombres,
            grupoAdetitss: d.grupoAdetitss,
            cantidad_tablas: cantidad,
            registrado_por: user?.id,
          },
          { context: conMensaje('Registrando la venta...') },
        ),
      );
      if (resp.success) {
        const seriales = resp.participante?.seriales || [];
        alert(
          `Participante creado. Tablas asignadas (${seriales.length}): ${seriales.join(', ')}\n` +
            `Total a pagar: $${resp.participante?.total_pagar ?? this.totalPagar()}\n` +
            `Las tablas se envían por correo a ${correo}.`,
        );
        this.volver();
      } else {
        alert(resp.message || 'Error al crear el participante');
      }
    } catch (err) {
      if (isConflict(err)) {
        // Otra venta se llevó las tablas o la cédula ya fue registrada: avisar y refrescar.
        const body = errorBody<{ sin_tablas?: boolean; cedula_registrada?: boolean }>(err);
        alert(
          errorMessage(err, 'Otro vendedor acaba de vender esas tablas.') +
            (body?.sin_tablas ? '\nSe actualizó la vista previa de la cola.' : ''),
        );
        if (body?.cedula_registrada) await this.buscarExistente(d.cedula.trim());
        void this.verCola();
      } else {
        alert(errorMessage(err, 'Error al guardar la venta. Por favor, intente nuevamente.'));
      }
    } finally {
      this.guardando.set(false);
    }
  }
}
