// Agregar cartones (tablas) a un participante existente.
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ArrowLeft, LucideAngularModule, Save } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorMessage, isConflict } from '../core/http';
import { SessionService } from '../core/session';
import { calcularTotal, textoPromociones } from '../core/tablas';

@Component({
  selector: 'app-add-carton',
  imports: [LucideAngularModule],
  template: `
    <div class="p-6 lg:p-10">
      <button
        type="button"
        (click)="volver()"
        class="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-8"
      >
        <lucide-icon [img]="ArrowLeftIcon" [size]="20" /> Volver
      </button>

      <div class="max-w-lg mx-auto">
        <h1 class="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          Añadir Cartones de Bingo
        </h1>
        <p class="text-gray-600 dark:text-gray-300 mb-8">
          Indique cuántas tablas más compra el participante.
        </p>

        <form (submit)="enviar($event)" class="bg-white dark:bg-gray-900 rounded-lg p-6 border">
          <p class="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Las tablas se entregan en orden: al guardar se asignan las siguientes disponibles de la
            cola.
          </p>
          <label class="block text-gray-700 dark:text-gray-300 mb-2" for="cantidad"
            >Cantidad de tablas a añadir</label
          >
          <input
            id="cantidad"
            type="number"
            min="1"
            [value]="cantidad()"
            (input)="cantidad.set(+$any($event.target).value || 0)"
            class="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
          />
          <div class="mt-6 text-right">
            <p class="text-lg font-semibold text-gray-800 dark:text-gray-100">
              Total a pagar: <span class="text-blue-600">\${{ total() }}</span>
            </p>
            <!-- La promoción se calcula sobre todas las tablas del participante. -->
            <p class="text-sm text-gray-500 dark:text-gray-400">
              Ya tiene {{ actuales() }} tabla(s) (\${{ pagadoAntes() }}). Con estas quedan
              {{ actuales() + cantidad() }} → \${{ totalNuevo() }}
              @if (promociones()) {
                ({{ promociones() }})
              }
            </p>
          </div>
          <div class="mt-8 flex justify-end gap-4">
            <button
              type="button"
              (click)="volver()"
              class="px-4 py-2.5 border rounded-lg font-bold hover:bg-gray-100 dark:text-white"
            >
              Cancelar
            </button>
            <button
              type="submit"
              [disabled]="loading()"
              class="flex items-center gap-2 bg-blue-600 text-white px-4 py-2.5 rounded-lg font-bold hover:bg-blue-700 disabled:opacity-60"
            >
              <lucide-icon [img]="SaveIcon" [size]="16" />
              {{ loading() ? 'Guardando...' : 'Guardar Cartones' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  `,
})
export class AddCarton implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly session = inject(SessionService);
  protected readonly ArrowLeftIcon = ArrowLeft;
  protected readonly SaveIcon = Save;

  /** Parámetro de ruta :userId (id del participante). */
  readonly userId = input.required<string>();

  /** Tablas a añadir; se toman de la cola al guardar. */
  protected readonly cantidad = signal(1);
  protected readonly loading = signal(false);
  /** Tablas que el participante ya tiene (la promoción cuenta todas). */
  protected readonly actuales = signal(0);
  protected readonly pagadoAntes = computed(() => calcularTotal(this.actuales()));
  protected readonly totalNuevo = computed(() => calcularTotal(this.actuales() + this.cantidad()));
  /** Lo que se cobra ahora: la diferencia, igual que el servidor. */
  protected readonly total = computed(() => this.totalNuevo() - this.pagadoAntes());
  protected readonly promociones = computed(() =>
    textoPromociones(this.actuales() + this.cantidad()),
  );

  async ngOnInit(): Promise<void> {
    try {
      const resp = await firstValueFrom(
        this.http.get<{ tablas?: unknown[] }>(`/api/obtenerTablasParticipante/${this.userId()}`),
      );
      this.actuales.set(resp.tablas?.length || 0);
    } catch {
      this.actuales.set(0);
    }
  }

  protected volver(): void {
    void this.router.navigate(['/admin/user', this.userId(), 'cartones']);
  }

  protected async enviar(event: Event): Promise<void> {
    event.preventDefault();
    if (this.loading()) return; // ignora clics repetidos mientras se guarda
    const cantidad = this.cantidad();
    if (cantidad <= 0) {
      alert('Indique cuántas tablas añadir');
      return;
    }
    const user = this.session.user();
    this.loading.set(true);
    try {
      const resp = await firstValueFrom(
        this.http.post<{ success: boolean; message?: string; seriales?: string[] }>(
          `/api/participante/${this.userId()}/tablas/${user?.tipo_usuario}`,
          { cantidad, usuario_id: user?.id },
        ),
      );
      if (resp.success) {
        alert(
          `Tablas agregadas: ${(resp.seriales || []).join(', ')}\nCobrar: $${this.total()}\n` +
            'Se envía por correo la lista actualizada de tablas.',
        );
        this.volver();
      } else {
        alert(resp.message || 'Error al agregar tablas');
      }
    } catch (err) {
      alert(errorMessage(err, 'Error al agregar tablas'));
      // 409: otra venta se llevó las tablas; se vuelve a leer lo que tiene el participante.
      if (isConflict(err)) await this.ngOnInit();
    } finally {
      this.loading.set(false);
    }
  }
}
