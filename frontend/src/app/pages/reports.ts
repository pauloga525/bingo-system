// Reportes y ventas generales (solo admin).
import { NgTemplateOutlet } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  Component,
  ElementRef,
  OnInit,
  computed,
  effect,
  inject,
  signal,
  viewChildren,
} from '@angular/core';
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Legend,
  LinearScale,
  Title,
  Tooltip,
} from 'chart.js';
import {
  Award,
  BarChart3,
  DollarSign,
  LucideAngularModule,
  LucideIconData,
  Tag,
  Ticket,
  Trophy,
  Users,
} from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Title, Tooltip, Legend);

type PromoKey = 'paquete_5' | 'paquete_2' | 'suelta';

interface Ventas {
  participantes: number;
  tablas: number;
  monto: number;
  promociones: Record<PromoKey, number>;
}

interface VentaRol extends Ventas {
  rol: string;
  nombre: string;
  vendedores: number;
}

interface VentaVendedor extends Ventas {
  id: string;
  nombre: string;
  usuario?: string;
  rol: string;
  rol_nombre: string;
}

interface Promocion {
  tablas: number;
  precio: number;
  cantidad: number;
  tablas_en_promocion: number;
  monto: number;
}

interface Reportes {
  tablas_vendidas: number;
  dinero_recaudado: number;
  promociones: Record<PromoKey, Promocion>;
  ventas_por_rol: VentaRol[];
  ventas_por_vendedor: VentaVendedor[];
  total_tablas: number;
  tablas_ganadoras: number;
  total_participantes: number;
  participantes_con_ganadores: number;
  tasa_ganadores: number;
  total_vendido: number;
  ventas_por_usuario?: Record<string, number>;
  ventas_por_grupo?: Record<string, number>;
  grupo_top?: { nombre?: string; total?: number };
  usuario_top?: { nombre?: string; total?: number };
}

interface Tarjeta {
  icon: LucideIconData;
  title: string;
  value: string | number;
  /** Clases del fondo y del ícono (Tailwind necesita los nombres completos). */
  bg: string;
  fg: string;
}

interface Grafico {
  title: string;
  label: string;
  data: Record<string, number>;
  color: string;
}

@Component({
  selector: 'app-reports',
  imports: [NgTemplateOutlet, LucideAngularModule],
  template: `
    @if (loading()) {
      <div class="p-10 text-center text-gray-600">Cargando...</div>
    } @else if (!reportes()) {
      <div class="p-6 lg:p-10">
        <div class="bg-yellow-100 border border-yellow-400 text-yellow-700 px-4 py-3 rounded">
          No se pudieron cargar los reportes.
        </div>
      </div>
    } @else {
      <div class="p-6 lg:p-10">
        <h1 class="text-3xl font-bold text-gray-900 dark:text-white mb-8">
          Reportes y Ventas Generales
        </h1>

        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          @for (t of resumen(); track t.title) {
            <ng-container [ngTemplateOutlet]="card" [ngTemplateOutletContext]="{ $implicit: t }" />
          }
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-10">
          @for (t of ventas(); track t.title) {
            <ng-container [ngTemplateOutlet]="card" [ngTemplateOutletContext]="{ $implicit: t }" />
          }
        </div>

        <!-- Promociones vendidas -->
        <div class="bg-white dark:bg-gray-900 p-6 rounded-lg border shadow-sm mb-10">
          <h2 class="text-xl font-bold text-gray-900 dark:text-white mb-1">Promociones vendidas</h2>
          <p class="text-sm text-gray-500 mb-4">
            Por participante: paquetes de 5 por $10, luego pares por $5 y la suelta a $3.
          </p>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            @for (p of promos(); track p.key) {
              <div class="rounded-lg bg-gray-50 dark:bg-gray-800 p-4">
                <p class="text-sm text-gray-600 dark:text-gray-300">{{ p.titulo }}</p>
                <p class="text-3xl font-bold text-gray-900 dark:text-white">{{ p.cantidad }}</p>
                <p class="text-xs text-gray-500 dark:text-gray-400">
                  {{ p.tablas_en_promocion }} tablas · \${{ p.monto }}
                </p>
              </div>
            }
          </div>
        </div>

        <!-- Ventas por rol -->
        <div class="bg-white dark:bg-gray-900 p-6 rounded-lg border shadow-sm mb-10">
          <h2 class="text-xl font-bold text-gray-900 dark:text-white mb-4">Ventas por rol</h2>
          <div class="overflow-x-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200">
                <tr>
                  @for (h of headersRol; track $index) {
                    <th class="px-3 py-2" [class]="$index ? 'text-right' : 'text-left'">
                      {{ h }}
                    </th>
                  }
                </tr>
              </thead>
              <tbody class="text-gray-800 dark:text-gray-100">
                @for (r of reportes()?.ventas_por_rol || []; track r.rol) {
                  <tr class="border-t border-gray-200 dark:border-gray-700">
                    <td class="px-3 py-2 font-medium">{{ r.nombre }}</td>
                    <td class="px-3 py-2 text-right">{{ r.vendedores }}</td>
                    <td class="px-3 py-2 text-right">{{ r.participantes }}</td>
                    <td class="px-3 py-2 text-right font-semibold">{{ r.tablas }}</td>
                    <td class="px-3 py-2 text-right">\${{ r.monto }}</td>
                    <td class="px-3 py-2 text-right">{{ r.promociones.paquete_5 }}</td>
                    <td class="px-3 py-2 text-right">{{ r.promociones.paquete_2 }}</td>
                    <td class="px-3 py-2 text-right">{{ r.promociones.suelta }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>

        <!-- Ventas por vendedor -->
        <div class="bg-white dark:bg-gray-900 p-6 rounded-lg border shadow-sm mb-10">
          <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
            <h2 class="text-xl font-bold text-gray-900 dark:text-white">
              Ventas por vendedor / animador
            </h2>
            <div class="flex flex-wrap gap-2">
              <input
                [value]="buscar()"
                (input)="buscar.set($any($event.target).value)"
                placeholder="Buscar vendedor"
                class="border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg px-3 py-1.5 text-sm"
              />
              <select
                (change)="rolFiltro.set($any($event.target).value)"
                class="border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg px-3 py-1.5 text-sm"
              >
                <option value="">Todos los roles</option>
                @for (r of reportes()?.ventas_por_rol || []; track r.rol) {
                  <option [value]="r.rol">{{ r.nombre }}</option>
                }
              </select>
              <label class="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-300">
                <input
                  type="checkbox"
                  [checked]="soloConVentas()"
                  (change)="soloConVentas.set($any($event.target).checked)"
                />
                Solo con ventas
              </label>
            </div>
          </div>
          <div class="overflow-x-auto max-h-[32rem]">
            <table class="min-w-full text-sm">
              <thead
                class="bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200 sticky top-0"
              >
                <tr>
                  @for (h of headersVendedor; track $index) {
                    <th class="px-3 py-2" [class]="$index > 1 ? 'text-right' : 'text-left'">
                      {{ h }}
                    </th>
                  }
                </tr>
              </thead>
              <tbody class="text-gray-800 dark:text-gray-100">
                @for (v of vendedores(); track v.id) {
                  <tr class="border-t border-gray-200 dark:border-gray-700">
                    <td class="px-3 py-2">{{ v.nombre }}</td>
                    <td class="px-3 py-2">{{ v.rol_nombre }}</td>
                    <td class="px-3 py-2 text-right">{{ v.participantes }}</td>
                    <td class="px-3 py-2 text-right font-semibold">{{ v.tablas }}</td>
                    <td class="px-3 py-2 text-right">\${{ v.monto }}</td>
                    <td class="px-3 py-2 text-right">{{ v.promociones.paquete_5 }}</td>
                    <td class="px-3 py-2 text-right">{{ v.promociones.paquete_2 }}</td>
                    <td class="px-3 py-2 text-right">{{ v.promociones.suelta }}</td>
                  </tr>
                } @empty {
                  <tr>
                    <td
                      [attr.colspan]="headersVendedor.length"
                      class="px-3 py-4 text-center text-gray-500"
                    >
                      No hay vendedores para mostrar.
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>

        <div class="bg-white dark:bg-gray-900 p-6 rounded-lg border shadow-sm mb-10">
          <h2 class="text-xl font-bold text-gray-900 dark:text-white mb-4">
            Estadísticas Generales
          </h2>
          <p class="text-gray-600 dark:text-gray-300">
            Tasa de ganadores: {{ reportes()?.tasa_ganadores }}%
          </p>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-10">
          @for (g of graficos(); track g.title) {
            <div class="bg-white dark:bg-gray-900 p-6 rounded-lg border shadow-sm">
              <h3 class="text-lg font-bold mb-4 text-gray-900 dark:text-white">{{ g.title }}</h3>
              <canvas #chart></canvas>
            </div>
          }
        </div>
      </div>
    }

    <ng-template #card let-t>
      <div class="bg-white dark:bg-gray-900 p-6 rounded-lg border shadow-sm">
        <div class="flex items-center gap-3">
          <div class="p-3 rounded-lg" [class]="t.bg">
            <lucide-icon [img]="t.icon" [size]="24" [class]="t.fg" />
          </div>
          <div>
            <p class="text-sm text-gray-600">{{ t.title }}</p>
            <p class="text-lg font-bold text-gray-900 dark:text-white break-words">{{ t.value }}</p>
          </div>
        </div>
      </div>
    </ng-template>
  `,
})
export class Reports implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly canvases = viewChildren<ElementRef<HTMLCanvasElement>>('chart');
  private charts: Chart[] = [];

  protected readonly reportes = signal<Reportes | null>(null);
  protected readonly loading = signal(true);
  protected readonly resumen = signal<Tarjeta[]>([]);
  protected readonly ventas = signal<Tarjeta[]>([]);
  protected readonly graficos = signal<Grafico[]>([]);
  protected readonly buscar = signal('');
  protected readonly rolFiltro = signal('');
  protected readonly soloConVentas = signal(false);
  protected readonly headersRol = [
    'Rol',
    'Vendedores',
    'Participantes',
    'Tablas',
    'Dinero',
    '5 por $10',
    '2 por $5',
    '1 por $3',
  ];
  protected readonly headersVendedor = [
    'Vendedor',
    'Rol',
    'Participantes',
    'Tablas',
    'Dinero',
    '5 por $10',
    '2 por $5',
    '1 por $3',
  ];
  protected readonly promos = computed(() => {
    const p = this.reportes()?.promociones;
    if (!p) return [];
    return [
      { key: 'paquete_5', titulo: 'Paquetes 5 tablas por $10', ...p.paquete_5 },
      { key: 'paquete_2', titulo: 'Paquetes 2 tablas por $5', ...p.paquete_2 },
      { key: 'suelta', titulo: 'Tablas sueltas a $3', ...p.suelta },
    ];
  });
  protected readonly vendedores = computed(() => {
    const q = this.buscar().trim().toLowerCase();
    const rol = this.rolFiltro();
    return (this.reportes()?.ventas_por_vendedor || []).filter(
      (v) =>
        (!rol || v.rol === rol) &&
        (!this.soloConVentas() || v.tablas > 0) &&
        (!q || `${v.nombre} ${v.usuario || ''}`.toLowerCase().includes(q)),
    );
  });

  constructor() {
    // Dibuja los gráficos cuando sus <canvas> aparecen en la vista.
    effect((onCleanup) => {
      const canvases = this.canvases();
      const graficos = this.graficos();
      this.charts = canvases.map(
        (c, i) =>
          new Chart(c.nativeElement, {
            type: 'bar',
            data: {
              labels: Object.keys(graficos[i]?.data || {}),
              datasets: [
                {
                  label: graficos[i]?.label,
                  data: Object.values(graficos[i]?.data || {}),
                  backgroundColor: graficos[i]?.color,
                },
              ],
            },
            options: { responsive: true, plugins: { legend: { display: true } } },
          }),
      );
      onCleanup(() => this.charts.forEach((ch) => ch.destroy()));
    });
  }

  async ngOnInit(): Promise<void> {
    try {
      const resp = await firstValueFrom(
        this.http.get<{ success: boolean; reportes?: Reportes }>('/api/reportes'),
      );
      if (resp.success && resp.reportes) this.mostrar(resp.reportes);
    } catch (err) {
      console.error('Error al cargar reportes:', err);
    } finally {
      this.loading.set(false);
    }
  }

  private mostrar(r: Reportes): void {
    this.resumen.set([
      {
        icon: BarChart3,
        title: 'Total Tablas',
        value: r.total_tablas,
        bg: 'bg-blue-100',
        fg: 'text-blue-600',
      },
      {
        icon: Award,
        title: 'Ganadoras',
        value: r.tablas_ganadoras,
        bg: 'bg-green-100',
        fg: 'text-green-600',
      },
      {
        icon: Users,
        title: 'Total Participantes',
        value: r.total_participantes,
        bg: 'bg-purple-100',
        fg: 'text-purple-600',
      },
      {
        icon: Award,
        title: 'Con Ganadores',
        value: r.participantes_con_ganadores,
        bg: 'bg-yellow-100',
        fg: 'text-yellow-600',
      },
    ]);
    this.ventas.set([
      {
        icon: Ticket,
        title: 'Tablas vendidas',
        value: Number(r.tablas_vendidas ?? r.total_vendido ?? 0).toLocaleString(),
        bg: 'bg-sky-100',
        fg: 'text-sky-600',
      },
      {
        icon: DollarSign,
        title: 'Dinero recaudado (con promociones)',
        value: `$${Number(r.dinero_recaudado || 0).toLocaleString()}`,
        bg: 'bg-emerald-100',
        fg: 'text-emerald-600',
      },
      {
        icon: Tag,
        title: 'Promociones vendidas',
        value:
          (r.promociones?.paquete_5?.cantidad || 0) + (r.promociones?.paquete_2?.cantidad || 0),
        bg: 'bg-indigo-100',
        fg: 'text-indigo-600',
      },
      {
        icon: Trophy,
        title: 'Grupo con Más Ventas',
        value: `${r.grupo_top?.nombre || 'N/A'} ($${r.grupo_top?.total || 0})`,
        bg: 'bg-orange-100',
        fg: 'text-orange-600',
      },
      {
        icon: Trophy,
        title: 'Usuario con Más Ventas',
        value: `${r.usuario_top?.nombre || 'N/A'} ($${r.usuario_top?.total || 0})`,
        bg: 'bg-pink-100',
        fg: 'text-pink-600',
      },
    ]);
    this.graficos.set([
      {
        title: 'Tablas vendidas por rol',
        label: 'Tablas',
        data: Object.fromEntries((r.ventas_por_rol || []).map((x) => [x.nombre, x.tablas])),
        color: 'rgba(99, 102, 241, 0.7)',
      },
      {
        title: 'Ventas por Usuario',
        label: 'Ventas por Usuario ($)',
        data: r.ventas_por_usuario || {},
        color: 'rgba(59, 130, 246, 0.7)',
      },
      {
        title: 'Ventas por Grupo',
        label: 'Ventas por Grupo ($)',
        data: r.ventas_por_grupo || {},
        color: 'rgba(34, 197, 94, 0.7)',
      },
    ]);
    this.reportes.set(r);
  }
}
