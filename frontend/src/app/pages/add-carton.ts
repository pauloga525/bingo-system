// Agregar cartones (tablas) a un participante existente.
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ArrowLeft, LucideAngularModule, Plus, Save, X } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorMessage } from '../core/http';
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
          Agregue los códigos de los cartones de bingo. Puede agregar tantos como necesite.
        </p>

        <form (submit)="enviar($event)" class="bg-white dark:bg-gray-900 rounded-lg p-6 border">
          <div class="space-y-4 mb-6">
            @for (carton of cartones(); track $index) {
              <div class="flex items-center gap-2">
                <input
                  type="text"
                  [value]="carton"
                  (input)="setCarton($index, $event)"
                  placeholder="Ingrese el código del cartón"
                  class="flex-1 py-2.5 px-4 border rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:text-white"
                />
                <button
                  type="button"
                  (click)="quitar($index)"
                  class="w-10 h-10 flex items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100"
                >
                  <lucide-icon [img]="XIcon" [size]="20" />
                </button>
              </div>
            }
          </div>

          <button
            type="button"
            (click)="cartones.update((c) => [...c, ''])"
            class="w-full flex items-center justify-center gap-2 border-2 border-dashed border-blue-600 py-2.5 rounded-lg text-blue-600 font-bold hover:bg-blue-50"
          >
            <lucide-icon [img]="PlusIcon" [size]="16" /> Agregar Cartón
          </button>
          <div class="mt-6 text-right">
            <p class="text-lg font-semibold text-gray-800 dark:text-gray-100">
              Total a pagar: <span class="text-blue-600">\${{ total() }}</span>
            </p>
            <!-- La promoción se calcula sobre todas las tablas del participante. -->
            <p class="text-sm text-gray-500 dark:text-gray-400">
              Ya tiene {{ actuales() }} tabla(s) (\${{ pagadoAntes() }}). Con estas quedan
              {{ actuales() + validos().length }} → \${{ totalNuevo() }}
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
  protected readonly PlusIcon = Plus;
  protected readonly SaveIcon = Save;
  protected readonly XIcon = X;

  /** Parámetro de ruta :userId (id del participante). */
  readonly userId = input.required<string>();

  protected readonly cartones = signal<string[]>(['', '']);
  protected readonly loading = signal(false);
  /** Tablas que el participante ya tiene (la promoción cuenta todas). */
  protected readonly actuales = signal(0);
  protected readonly validos = computed(() =>
    this.cartones()
      .map((c) => c.trim())
      .filter(Boolean),
  );
  protected readonly pagadoAntes = computed(() => calcularTotal(this.actuales()));
  protected readonly totalNuevo = computed(() =>
    calcularTotal(this.actuales() + this.validos().length),
  );
  /** Lo que se cobra ahora: la diferencia, igual que el servidor. */
  protected readonly total = computed(() => this.totalNuevo() - this.pagadoAntes());
  protected readonly promociones = computed(() =>
    textoPromociones(this.actuales() + this.validos().length),
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

  protected setCarton(index: number, event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.cartones.update((c) => c.map((v, i) => (i === index ? value : v)));
  }

  protected quitar(index: number): void {
    if (this.cartones().length > 1) this.cartones.update((c) => c.filter((_, i) => i !== index));
  }

  protected async enviar(event: Event): Promise<void> {
    event.preventDefault();
    const tablas = this.validos();
    if (!tablas.length) {
      alert('Debe ingresar al menos un código de tabla');
      return;
    }
    const user = this.session.user();
    this.loading.set(true);
    try {
      // Validar que cada tabla exista y esté disponible.
      for (const tabla of tablas) {
        try {
          const resp = await firstValueFrom(
            this.http.get<{ success: boolean; tabla?: { disponible?: boolean } }>(
              `/api/validarTabla/${encodeURIComponent(tabla)}`,
            ),
          );
          if (!resp.success || !resp.tabla?.disponible) {
            alert(`La tabla ${tabla} no está disponible o no existe`);
            return;
          }
        } catch (err) {
          alert(`Error al validar la tabla ${tabla}: ${errorMessage(err, 'Tabla no encontrada')}`);
          return;
        }
      }

      const resp = await firstValueFrom(
        this.http.post<{ success: boolean; message?: string }>(
          `/api/participante/${this.userId()}/tablas/${user?.tipo_usuario}`,
          { tablas, usuario_id: user?.id, user_tipo_usuario: user?.tipo_usuario },
        ),
      );
      if (resp.success) {
        alert('Tablas agregadas correctamente');
        this.volver();
      } else {
        alert(resp.message || 'Error al agregar tablas');
      }
    } catch (err) {
      alert(errorMessage(err, 'Error al agregar tablas'));
    } finally {
      this.loading.set(false);
    }
  }
}
