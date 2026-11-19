// CRUD de animadores (solo admin). El correo es el que le permite iniciar sesión con Google.
// Cada animador tiene como máximo un curso (paralelo) y cada curso como máximo un animador.
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { Edit, LucideAngularModule, Plus, Search, Trash2 } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorBody, errorMessage, onlyDigits } from '../core/http';
import { SessionService } from '../core/session';
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
  correo: string;
  curso_asignado: boolean;
  usuario: string | null;
  usuario_id: string | null;
  reserva: { total: number; usadas: number; desde: string; hasta: string } | null;
}

interface Curso extends CursoBase {
  estudiantes: number;
  animador: string | null;
  animador_id: string | null;
}

type Filtro = 'todos' | 'con' | 'sin';

/** Clave única de un curso para la lista desplegable ('' = sin curso). */
const cursoKey = (c: CursoBase): string =>
  c.curso && c.paralelo ? [c.curso, c.especialidad || '', c.nivel, c.paralelo].join('|') : '';

const cursoNombre = (c: CursoBase): string =>
  [c.curso, c.especialidad, `${c.nivel}°`, c.paralelo].filter(Boolean).join(' · ');

const HEADERS = ['Nombre', 'Correo', 'Curso asignado', 'Usuario', 'Tablas', ''];

@Component({
  selector: 'app-animadores-admin',
  imports: [LucideAngularModule, CrudForm],
  template: `
    <div class="p-6 max-w-6xl mx-auto">
      <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Animadores</h1>
          <p class="text-sm text-gray-600 dark:text-gray-400">
            {{ animadores().length }} registrados · {{ conAcceso() }} con correo (pueden iniciar
            sesión) · {{ cursosLibres() }} de {{ cursos().length }} cursos sin animador
          </p>
        </div>
        <button
          type="button"
          (click)="editing.set({ cursoKey: '' })"
          class="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"
        >
          <lucide-icon [img]="PlusIcon" [size]="16" /> Nuevo animador
        </button>
      </div>

      <div class="flex flex-wrap gap-2 mb-4">
        <form (submit)="$event.preventDefault(); cargar()" class="flex gap-2">
          <input
            [value]="search()"
            (input)="search.set($any($event.target).value)"
            placeholder="Buscar por nombre, correo, curso o paralelo"
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
          <option value="con">Con curso</option>
          <option value="sin">Sin curso</option>
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
                    } @else {
                      <span
                        class="text-xs bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200 px-2 py-0.5 rounded"
                        >Sin curso</span
                      >
                    }
                  </td>
                  <td class="px-3 py-2">{{ a.usuario || '—' }}</td>
                  <td class="px-3 py-2 whitespace-nowrap">
                    @if (a.reserva; as r) {
                      <span [title]="'Usadas ' + r.usadas + ' de ' + r.total">
                        {{ r.desde }} – {{ r.hasta }} ({{ r.usadas }}/{{ r.total }})
                      </span>
                    } @else {
                      <button
                        type="button"
                        (click)="reservar(a)"
                        class="text-sm text-blue-600 hover:underline"
                      >
                        Reservar
                      </button>
                    }
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
                    No hay animadores para mostrar.
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }

      @if (editing(); as e) {
        <app-crud-form
          [title]="e['_id'] ? 'Editar animador' : 'Nuevo animador'"
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
  private readonly session = inject(SessionService);
  protected readonly PlusIcon = Plus;
  protected readonly SearchIcon = Search;
  protected readonly EditIcon = Edit;
  protected readonly TrashIcon = Trash2;
  protected readonly headers = HEADERS;
  protected readonly nombreCurso = cursoNombre;

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
  protected readonly visibles = computed(() => {
    const f = this.filtro();
    return this.animadores().filter((a) =>
      f === 'todos' ? true : f === 'con' ? a.curso_asignado : !a.curso_asignado,
    );
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
        name: 'cursoKey',
        label: 'Curso (paralelo)',
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
    this.editing.set({ _id: a._id, nombre: a.nombre, correo: a.correo, cursoKey: cursoKey(a) });
  }

  protected readonly guardar = async (values: CrudValues): Promise<void> => {
    const [curso = '', especialidad = '', nivel = '', paralelo = ''] = String(
      values['cursoKey'] || '',
    ).split('|');
    const payload: Record<string, unknown> = {
      nombre: values['nombre'],
      correo: values['correo'] || '',
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

  /** Reserva un bloque de tablas libres a la cuenta del animador (solo admin). */
  protected async reservar(a: Animador): Promise<void> {
    if (!a.usuario_id) {
      alert('Este animador aún no tiene cuenta. Edítelo y guarde para crearla.');
      return;
    }
    const cantidad = parseInt(onlyDigits(prompt(`¿Cuántas tablas reservar para ${a.nombre}?`)), 10);
    if (!cantidad) return;
    try {
      const data = await firstValueFrom(
        this.http.post<{ from: string; to: string }>(`/api/users/${a.usuario_id}/assign_tables`, {
          totalTables: cantidad,
          requesting_user_id: this.session.user()?.id,
        }),
      );
      alert(`Tablas reservadas: ${data.from} a ${data.to}`);
      await this.cargar();
    } catch (err) {
      alert(errorMessage(err, 'No se pudo reservar.'));
    }
  }
}
