// Ayuda del login para estudiantes y público general: pasos cortos y descarga del instructivo
// en PDF (los PDF están en public/instructivos y se publican con el panel).
import { Component, OnInit, input, output, signal } from '@angular/core';

type Publico = 'uets' | 'externo';

@Component({
  selector: 'app-ayuda-login',
  host: { '(document:keydown.escape)': 'cerrar.emit()' },
  template: `
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4 py-6"
      (click)="cerrar.emit()"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="ayuda-titulo"
        class="w-full max-w-lg max-h-full overflow-y-auto bg-gray-950 border border-gray-700 rounded-2xl p-6 space-y-5 text-gray-200"
        (click)="$event.stopPropagation()"
      >
        <div class="flex items-start justify-between gap-4">
          <h3 id="ayuda-titulo" class="text-xl font-bold text-white">¿Cómo ver mis tablas?</h3>
          <button
            type="button"
            (click)="cerrar.emit()"
            aria-label="Cerrar"
            class="text-gray-400 hover:text-white text-2xl leading-none"
          >
            &times;
          </button>
        </div>

        <div class="grid grid-cols-2 gap-2 bg-gray-900 p-1 rounded-xl" role="tablist">
          <button
            type="button"
            role="tab"
            [attr.aria-selected]="publico() === 'uets'"
            (click)="publico.set('uets')"
            [class]="publico() === 'uets' ? tabActiva : tabInactiva"
          >
            Soy estudiante
          </button>
          <button
            type="button"
            role="tab"
            [attr.aria-selected]="publico() === 'externo'"
            (click)="publico.set('externo')"
            [class]="publico() === 'externo' ? tabActiva : tabInactiva"
          >
            Público general
          </button>
        </div>

        @if (publico() === 'uets') {
          <ol class="list-decimal pl-5 space-y-2 text-sm">
            <li>
              Deja marcada la pestaña <b>Estudiante / personal UETS</b> y pulsa
              <b>Iniciar sesión con Google</b>.
            </li>
            <li>
              Elige tu cuenta de estudiante <b>…est&#64;uets.edu.ec</b> (no una cuenta personal de
              Gmail).
            </li>
            <li>
              Solo la primera vez: escribe tu cédula, nombres y apellidos tal como constan en
              secretaría y pulsa <b>Registrarme</b>.
            </li>
            <li>Verás tus tablas. Pulsa <b>Descargar PDF</b> para guardarlas o imprimirlas.</li>
          </ol>
          <p class="text-xs text-gray-400">
            Si no ves tus tablas, consulta a tu animador de curso: él registra tu compra con tu
            cédula.
          </p>
        } @else {
          <ol class="list-decimal pl-5 space-y-2 text-sm">
            <li>Pulsa la pestaña <b>Público general</b>.</li>
            <li>
              Escribe la <b>cédula y el correo que diste al comprar</b> y pulsa
              <b>Enviar código</b>.
            </li>
            <li>
              Revisa tu correo (y la carpeta de spam): te llega un código de 6 dígitos que vale 10
              minutos.
            </li>
            <li>Escribe el código y pulsa <b>Ver mis tablas</b>. Desde ahí puedes descargarlas.</li>
          </ol>
          <p class="text-xs text-gray-400">
            No necesitas crear una cuenta. Si no llega el código, revisa que la cédula y el correo
            sean exactamente los de tu compra.
          </p>
        }

        <a
          [href]="publico() === 'uets' ? pdfEstudiantes : pdfPublico"
          [attr.download]="
            publico() === 'uets'
              ? 'Instructivo Bingo UETS - Estudiantes.pdf'
              : 'Instructivo Bingo UETS - Publico general.pdf'
          "
          target="_blank"
          rel="noopener"
          class="flex items-center justify-center gap-2 w-full bg-yellow-500 hover:bg-yellow-400 text-gray-900 font-semibold rounded-lg px-4 py-2.5"
        >
          <svg
            class="h-5 w-5"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            viewBox="0 0 24 24"
          >
            <path d="M12 3v12m0 0-4-4m4 4 4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
          </svg>
          Descargar instructivo completo (PDF)
        </a>
      </div>
    </div>
  `,
})
export class AyudaLogin implements OnInit {
  /** Pestaña del login desde la que se abrió la ayuda. */
  readonly inicial = input<Publico>('uets');
  readonly cerrar = output<void>();

  protected readonly publico = signal<Publico>('uets');
  protected readonly pdfEstudiantes = 'instructivos/instructivo-estudiantes.pdf';
  protected readonly pdfPublico = 'instructivos/instructivo-publico-general.pdf';
  protected readonly tabActiva =
    'py-2 rounded-lg text-sm font-semibold bg-yellow-500 text-gray-900';
  protected readonly tabInactiva = 'py-2 rounded-lg text-sm text-gray-300 hover:bg-gray-800';

  ngOnInit(): void {
    this.publico.set(this.inicial());
  }
}
