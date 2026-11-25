// CRUD de vendedores (solo admin): animadores y los roles secretaría, financiero, parroquia
// y oratorio. El correo es el que le permite iniciar sesión con Google.
// Cada animador tiene como máximo un curso (paralelo) y cada curso como máximo un animador.
// Los demás roles no tienen curso y solo venden a externos.
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { Edit, LucideAngularModule, Plus, Search, Trash2 } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorBody, errorMessage } from '../core/http';
import { CARGOS } from '../core/session';
import { CrudField, CrudForm, CrudOption, CrudValues } from '../shared/crud-form';

interface CursoBase {
  curso: string;
  especialidad: string;
  nivel: number | string;
  paralelo: string;
}

interface Animador extends CursoBase {
  _id: string;
  nombre: string;
  rol: string;
  rol_nombre: string;
  correo: string;
  curso_asignado: boolean;
  usuario: string | null;
  usuario_id: string | null;
  /** Tablas vendidas y monto (las tablas se venden en cola, sin reservas). */
  ventas?: { tablas: number; monto: number };
}

interface Curso extends CursoBase {
  estudiantes: number;
  animador: string | null;
  animador_id: string | null;
}

/** 'todos', 'con' / 'sin' (curso) o 'rol:<rol>'. */
type Filtro = string;
const ROL_OPCIONES: CrudOption[] = Object.entries(CARGOS).map(([value, label]) => ({
  value,
  label: value === 'animador' ? `${label} (tiene curso)` : `${label} (solo externos)`,
}));

/** Clave única de un curso para la lista desplegable ('' = sin curso). */
const cursoKey = (c: CursoBase): string =>
  c.curso && c.paralelo ? [c.curso, c.especialidad || '', c.nivel, c.paralelo].join('|') : '';

const cursoNombre = (c: CursoBase): string =>
  [c.curso, c.especialidad, `${c.nivel}°`, c.paralelo].filter(Boolean).join(' · ');

const HEADERS = ['Nombre', 'Rol', 'Correo', 'Curso asignado', 'Usuario', 'Vendidas', ''];

@Component({
  selector: 'app-animadores-admin',
  imports: [LucideAngularModule, CrudForm],
  template: `
    <div class="p-6 max-w-6xl mx-auto">
      <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Vendedores</h1>
          <p class="text-sm text-gray-600 dark:text-gray-400">
            {{ animadores().length }} registrados · {{ conAcceso() }} con correo (pueden iniciar
            sesión) · {{ cursosLibres() }} de {{ cursos().length }} cursos sin animador
          </p>
          <p class="text-xs text-gray-500 dark:text-gray-400">
            Por rol:
            @for (r of porRol(); track r.rol; let last = $last) {
              {{ r.nombre }} {{ r.n }}{{ last ? '' : ' · ' }}
            }
          </p>
        </div>
        <button
          type="button"
          (click)="editing.set({ cursoKey: '', rol: 'animador' })"
          class="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"
        >
          <lucide-icon [img]="PlusIcon" [size]="16" /> Nuevo vendedor
        </button>
      </div>

      <div class="flex flex-wrap gap-2 mb-4">
        <form (submit)="$event.preventDefault(); cargar()" class="flex gap-2">
          <input
            [value]="search()"
            (input)="search.set($any($event.target).value)"
            placeholder="Buscar por nombre, correo, rol, curso o paralelo"
            class="border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg px-3 py-2 w-80"
          />
          <button
            type="submit"
            class="flex items-center gap-1 bg-gray-200 dark:bg-gray-700 dark:text-white px-3 py-2 rounded-lg"
          >
            <lucide-icon [img]="SearchIcon" [size]="16" /> Buscar
          </button>
        </form>
        <select
          (change)="filtro.set($any($event.target).value)"
          class="border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg px-3 py-2"
        >
          <option value="todos">Todos</option>
          <option value="con">Animadores con curso</option>
          <option value="sin">Animadores sin curso</option>
          @for (r of rolOpciones; track r.value) {
            <option [value]="'rol:' + r.value">Rol: {{ r.label }}</option>
          }
        </select>
      </div>

      @if (error()) {
        <p class="text-red-600 mb-3">{{ error() }}</p>
      }
      @if (loading()) {
        <p class="text-gray-600">Cargando...</p>
      } @else {
        <div class="overflow-x-auto bg-white dark:bg-gray-800 rounded-xl shadow">
          <table class="min-w-full text-sm">
            <thead class="bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200">
              <tr>
                @for (h of headers; track $index) {
                  <th class="text-left px-3 py-2">{{ h }}</th>
                }
              </tr>
            </thead>
            <tbody class="text-gray-800 dark:text-gray-100">
              @for (a of visibles(); track a._id) {
                <tr class="border-t border-gray-200 dark:border-gray-700">
                  <td class="px-3 py-2">{{ a.nombre }}</td>
                  <td class="px-3 py-2 whitespace-nowrap">{{ a.rol_nombre || 'Animador' }}</td>
                  <td class="px-3 py-2">
                    @if (a.correo) {
                      {{ a.correo }}
                    } @else {
                      <span class="text-gray-400">sin acceso</span>
                    }
                  </td>
                  <td class="px-3 py-2">
                    @if (a.curso_asignado) {
                      {{ nombreCurso(a) }}
                    } @else if (a.rol && a.rol !== 'animador') {
                      <span
                        class="text-xs bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 px-2 py-0.5 rounded"
                        >Solo externos</span
                      >
                    } @else {
                      <span
                        class="text-xs bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200 px-2 py-0.5 rounded"
                        >Sin curso</span
                      >
                    }
                  </td>
                  <td class="px-3 py-2">{{ a.usuario || '—' }}</td>
                  <td class="px-3 py-2 whitespace-nowrap">
                    {{ a.ventas?.tablas || 0 }} (\${{ a.ventas?.monto || 0 }})
                  </td>
                  <td class="px-3 py-2 whitespace-nowrap">
                    <button
                      type="button"
                      (click)="editar(a)"
                      class="text-blue-600 hover:text-blue-800 mr-3"
                      title="Editar o cambiar de curso"
                    >
                      <lucide-icon [img]="EditIcon" [size]="16" />
                    </button>
                    <button
                      type="button"
                      (click)="eliminar(a)"
                      class="text-red-600 hover:text-red-800"
                      title="Eliminar"
                    >
                      <lucide-icon [img]="TrashIcon" [size]="16" />
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td [attr.colspan]="headers.length" class="px-3 py-4 text-center text-gray-500">
                    No hay vendedores para mostrar.
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }

      @if (editing(); as e) {
        <app-crud-form
          [title]="e['_id'] ? 'Editar vendedor' : 'Nuevo vendedor'"
          [fields]="fields()"
          [initial]="e"
          [save]="guardar"
          (closed)="editing.set(null)"
        />
      }
    </div>
  `,
})
export class AnimadoresAdmin implements OnInit {
  private readonly http = inject(HttpClient);
  protected readonly PlusIcon = Plus;
  protected readonly SearchIcon = Search;
  protected readonly EditIcon = Edit;
  protected readonly TrashIcon = Trash2;
  protected readonly headers = HEADERS;
  protected readonly nombreCurso = cursoNombre;
  protected readonly rolOpciones = ROL_OPCIONES;

  protected readonly animadores = signal<Animador[]>([]);
  protected readonly cursos = signal<Curso[]>([]);
  protected readonly search = signal('');
  protected readonly filtro = signal<Filtro>('todos');
  protected readonly loading = signal(true);
  protected readonly error = signal('');
  /** null = cerrado, {...} = nuevo o editar */
  protected readonly editing = signal<CrudValues | null>(null);

  protected readonly conAcceso = computed(() => this.animadores().filter((a) => a.correo).length);
  protected readonly cursosLibres = computed(() => this.cursos().filter((c) => !c.animador).length);
  protected readonly porRol = computed(() =>
    Object.entries(CARGOS).map(([rol, nombre]) => ({
      rol,
      nombre,
      n: this.animadores().filter((a) => (a.rol || 'animador') === rol).length,
    })),
  );
  protected readonly visibles = computed(() => {
    const f = this.filtro();
    const esAnimador = (a: Animador) => (a.rol || 'animador') === 'animador';
    return this.animadores().filter((a) => {
      if (f.startsWith('rol:')) return (a.rol || 'animador') === f.slice(4);
      if (f === 'con') return esAnimador(a) && a.curso_asignado;
      if (f === 'sin') return esAnimador(a) && !a.curso_asignado;
      return true;
    });
  });

  /** Campos del formulario; la lista de cursos marca cuáles ya tienen animador. */
  protected readonly fields = computed<CrudField[]>(() => {
    const editandoId = this.editing()?.['_id'];
    const opciones: CrudOption[] = [
      { value: '', label: '— Sin curso —' },
      ...this.cursos().map((c) => {
        const ocupado = c.animador && c.animador_id !== editandoId;
        return {
          value: cursoKey(c),
          label:
            `${cursoNombre(c)} (${c.estudiantes} alumnos)` +
            (ocupado ? ` — ocupado por ${c.animador}` : ' — libre'),
        };
      }),
    ];
    return [
      {
        name: 'nombre',
        label: 'Nombres completos',
        required: true,
        wide: true,
        placeholder: 'APELLIDOS NOMBRES',
      },
      {
        name: 'correo',
        label: 'Correo institucional',
        type: 'email',
        wide: true,
        placeholder: 'nombre@uets.edu.ec',
      },
      {
        name: 'rol',
        label: 'Rol',
        type: 'select',
        required: true,
        wide: true,
        options: ROL_OPCIONES,
      },
      {
        name: 'cursoKey',
        label: 'Curso (paralelo) — solo para animadores',
        type: 'select',
        wide: true,
        options: opciones,
      },
    ];
  });

  ngOnInit(): void {
    void this.cargar();
  }

  protected async cargar(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const [data, cursos] = await Promise.all([
        firstValueFrom(
          this.http.get<{ animadores?: Animador[] }>('/api/animadores', {
            params: { search: this.search() },
          }),
        ),
        firstValueFrom(this.http.get<{ cursos?: Curso[] }>('/api/cursos')),
      ]);
      this.animadores.set(data.animadores || []);
      this.cursos.set(cursos.cursos || []);
    } catch (err) {
      this.error.set(errorMessage(err, 'Error al cargar animadores.'));
    } finally {
      this.loading.set(false);
    }
  }

  protected editar(a: Animador): void {
    this.editing.set({
      _id: a._id,
      nombre: a.nombre,
      correo: a.correo,
      rol: a.rol || 'animador',
      cursoKey: cursoKey(a),
    });
  }

  protected readonly guardar = async (values: CrudValues): Promise<void> => {
    const rol = String(values['rol'] || 'animador');
    // Los roles distintos de animador no tienen curso: se envía vacío.
    const [curso = '', especialidad = '', nivel = '', paralelo = ''] = (
      rol === 'animador' ? String(values['cursoKey'] || '') : ''
    ).split('|');
    const payload: Record<string, unknown> = {
      nombre: values['nombre'],
      correo: values['correo'] || '',
      rol,
      curso,
      especialidad,
      nivel: nivel ? Number(nivel) : '',
      paralelo,
    };
    const id = values['_id'] ? String(values['_id']) : '';
    const enviar = (body: Record<string, unknown>) =>
      firstValueFrom(
        id ? this.http.put(`/api/animadores/${id}`, body) : this.http.post('/api/animadores', body),
      );
    try {
      await enviar(payload);
    } catch (err) {
      const body = errorBody<{ curso_ocupado?: boolean; animador_actual?: string }>(err);
      if (!body?.curso_ocupado) throw err;
      const ok = confirm(
        `${errorMessage(err, 'El curso ya tiene animador.')}\n\n` +
          `¿Reasignarlo? ${body.animador_actual || 'El animador actual'} quedará sin curso.`,
      );
      if (!ok) throw err;
      await enviar({ ...payload, reasignar: true });
    }
    await this.cargar();
  };

  protected async eliminar(a: Animador): Promise<void> {
    if (!confirm(`¿Eliminar al animador ${a.nombre}?`)) return;
    try {
      await firstValueFrom(this.http.delete(`/api/animadores/${a._id}`));
      await this.cargar();
    } catch (err) {
      alert(errorMessage(err, 'No se pudo eliminar.'));
    }
  }
}
