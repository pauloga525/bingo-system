// Imprime las tablas de un participante: descarga su PDF (con la sesión) y abre el
// diálogo de impresión del navegador sin salir de la página.
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { conMensaje } from './loading';

export async function imprimirTablas(http: HttpClient, cedula: string): Promise<void> {
  const blob = await firstValueFrom(
    http.get(`/api/participante/cedula/${encodeURIComponent(cedula)}/tablas_pdf`, {
      responseType: 'blob',
      context: conMensaje('Preparando las tablas para imprimir...'),
    }),
  );
  if (blob.type !== 'application/pdf')
    throw new Error('El participante no tiene tablas asignadas.');
  const url = URL.createObjectURL(blob);
  const frame = document.createElement('iframe');
  frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0';
  frame.src = url;
  frame.onload = () => {
    try {
      frame.contentWindow?.focus();
      frame.contentWindow?.print();
    } catch {
      window.open(url, '_blank'); // si el navegador no deja imprimir el iframe, se abre el PDF
    }
    // Se limpia después: el diálogo de impresión necesita el documento abierto.
    setTimeout(() => {
      frame.remove();
      URL.revokeObjectURL(url);
    }, 60_000);
  };
  document.body.appendChild(frame);
}
