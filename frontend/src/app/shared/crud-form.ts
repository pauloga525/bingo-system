// Formulario modal genérico para los CRUD de animadores y estudiantes.
import { Component, OnInit, input, output, signal } from '@angular/core';
import { LucideAngularModule, X } from 'lucide-angular';

import { errorMessage } from '../core/http';

export interface CrudField {
  name: string;
  label: string;
  type?: 'text' | 'email' | 'number';
  required?: boolean;
  placeholder?: string;
  wide?: boolean;
}

export type CrudValues = Record<string, unknown>;

@Component({
  selector: 'app-crud-form',
  imports: [LucideAngularModule],
  template: `
    <div class="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <form
        (submit)="submit($event)"
        class="bg-white dark:bg-gray-800 rounded-2xl shadow-xl w-full max-w-lg p-6 space-y-4"
      >
        <div class="flex items-center justify-between">
          <h3 class="text-lg font-bold text-gray-900 dark:text-white">{{ title() }}</h3>
          <button type="button" (click)="closed.emit()" class="text-gray-500 hover:text-gray-800">
            <lucide-icon [img]="XIcon" [size]="20" />
          </button>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          @for (f of fields(); track f.name) {
            <label class="text-sm text-gray-700 dark:text-gray-200" [class.sm:col-span-2]="f.wide">
              {{ f.label }}
              @if (f.required) {
                <span class="text-red-500"> *</span>
              }
              <input
                [type]="f.type || 'text'"
                [required]="!!f.required"
                [placeholder]="f.placeholder || ''"
                [value]="valueOf(f.name)"
                (input)="set(f.name, $event)"
                class="mt-1 w-full border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg px-3 py-2"
              />
            </label>
          }
        </div>
        @if (error()) {
          <p class="text-red-600 text-sm">{{ error() }}</p>
        }
        <div class="flex justify-end gap-2">
          <button
            type="button"
            (click)="closed.emit()"
            class="px-4 py-2 rounded-lg bg-gray-200 dark:bg-gray-700 dark:text-white"
          >
            Cancelar
          </button>
          <button
            type="submit"
            [disabled]="saving()"
            class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-60"
          >
            {{ saving() ? 'Guardando...' : 'Guardar' }}
          </button>
        </div>
      </form>
    </div>
  `,
})
export class CrudForm implements OnInit {
  readonly title = input.required<string>();
  readonly fields = input.required<CrudField[]>();
  readonly initial = input<CrudValues>({});
  /** Guarda los valores; si lanza un error HTTP se muestra su mensaje. */
  readonly save = input.required<(values: CrudValues) => Promise<unknown>>();
  readonly closed = output<void>();

  protected readonly XIcon = X;
  protected readonly values = signal<CrudValues>({});
  protected readonly error = signal('');
  protected readonly saving = signal(false);

  ngOnInit(): void {
    this.values.set({ ...this.initial() });
  }

  protected valueOf(name: string): string {
    const v = this.values()[name];
    return v === null || v === undefined ? '' : String(v);
  }

  protected set(name: string, event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.values.update((v) => ({ ...v, [name]: value }));
  }

  protected async submit(event: Event): Promise<void> {
    event.preventDefault();
    this.error.set('');
    this.saving.set(true);
    try {
      await this.save()(this.values());
      this.closed.emit();
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo guardar.'));
    } finally {
      this.saving.set(false);
    }
  }
}
