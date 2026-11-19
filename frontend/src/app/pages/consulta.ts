// Página pública (/consulta): quien compró tablas las consulta con su cédula.
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { LucideAngularModule, Search } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorMessage, onlyDigits } from '../core/http';
import { Tabla } from '../core/tablas';
import { TablasGrid } from '../shared/tablas-grid';

interface ParticipantePublico {
  nombre?: string;
  apellido?: string;
  tablas: Tabla[];
}

@Component({
  selector: 'app-consulta',
  imports: [RouterLink, LucideAngularModule, TablasGrid],
  template: `
    <div class="min-h-screen bg-gray-50 dark:bg-gray-900 p-6">
      <div class="max-w-5xl mx-auto">
        <div class="bg-white dark:bg-gray-800 rounded-2xl shadow p-6 mb-6">
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white mb-1">
            Consulta tus tablas de Bingo
          </h1>
          <p class="text-gray-600 dark:text-gray-300 mb-4">
            Ingresa la cédula con la que se registró la compra.
          </p>
          <form (submit)="$event.preventDefault(); buscar(cedula())" class="flex flex-wrap gap-2">
            <input
              type="text"
              inputmode="numeric"
              placeholder="Número de cédula"
              [value]="cedula()"
              (input)="setCedula($event)"
              maxlength="13"
              class="border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg px-3 py-2 w-64"
            />
            <button
              type="submit"
              [disabled]="loading()"
              class="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg disabled:opacity-60"
            >
              <lucide-icon [img]="SearchIcon" [size]="16" />
              {{ loading() ? 'Buscando...' : 'Consultar' }}
            </button>
          </form>
          @if (error()) {
            <p class="text-red-600 mt-3">{{ error() }}</p>
          }
        </div>

        @if (participante(); as p) {
          <div class="bg-white dark:bg-gray-800 rounded-2xl shadow p-6">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white mb-4">{{ nombre() }}</h2>
            <app-tablas-grid
              [tablas]="p.tablas"
              [titulo]="'Bingo UETS - ' + nombre()"
              [archivo]="archivo()"
            />
          </div>
        }

        <p class="text-center text-sm text-gray-500 mt-6">
          ¿Tienes cuenta institucional?
          <a routerLink="/login" class="text-blue-600 hover:underline">Inicia sesión</a>
        </p>
      </div>
    </div>
  `,
})
export class Consulta implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly route = inject(ActivatedRoute);
  protected readonly SearchIcon = Search;

  protected readonly cedula = signal('');
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly participante = signal<ParticipantePublico | null>(null);
  private readonly consultada = signal('');

  protected readonly nombre = computed(() => {
    const p = this.participante();
    return p ? `${p.nombre || ''} ${p.apellido || ''}`.trim() : '';
  });
  protected readonly archivo = computed(() => `tablas_${this.consultada()}.pdf`);

  ngOnInit(): void {
    const inicial = onlyDigits(this.route.snapshot.queryParamMap.get('cedula'));
    if (inicial) {
      this.cedula.set(inicial);
      void this.buscar(inicial);
    }
  }

  protected setCedula(event: Event): void {
    const el = event.target as HTMLInputElement;
    el.value = onlyDigits(el.value);
    this.cedula.set(el.value);
  }

  protected async buscar(valor: string): Promise<void> {
    const limpia = (valor || '').trim();
    this.error.set('');
    this.participante.set(null);
    if (!/^\d{6,13}$/.test(limpia)) {
      this.error.set('Ingrese un número de cédula válido (solo números).');
      return;
    }
    this.loading.set(true);
    try {
      const data = await firstValueFrom(
        this.http.get<{ participante: ParticipantePublico }>(
          `/api/consulta/${encodeURIComponent(limpia)}`,
        ),
      );
      this.consultada.set(limpia);
      this.participante.set(data.participante);
    } catch (err) {
      this.error.set(errorMessage(err, 'Error al consultar. Intente nuevamente.'));
    } finally {
      this.loading.set(false);
    }
  }
}
