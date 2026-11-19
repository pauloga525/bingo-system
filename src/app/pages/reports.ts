// Reportes y ventas generales (solo admin).
import { NgTemplateOutlet } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, ElementRef, OnInit, effect, inject, signal, viewChildren } from '@angular/core';
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
  Trophy,
  Users,
} from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Title, Tooltip, Legend);

interface Reportes {
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
        icon: DollarSign,
        title: 'Total Vendido',
        value: `$${Number(r.total_vendido || 0).toLocaleString()}`,
        bg: 'bg-emerald-100',
        fg: 'text-emerald-600',
      },
      {
        icon: Trophy,
        title: 'Grupo con Más Ventas',
        value: `${r.grupo_top?.nombre || 'N/A'} (${r.grupo_top?.total || 0} ventas)`,
        bg: 'bg-orange-100',
        fg: 'text-orange-600',
      },
      {
        icon: Trophy,
        title: 'Usuario con Más Ventas',
        value: `${r.usuario_top?.nombre || 'N/A'} (${r.usuario_top?.total || 0} ventas)`,
        bg: 'bg-pink-100',
        fg: 'text-pink-600',
      },
    ]);
    this.graficos.set([
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
