// Utilidades de tablas de bingo: matriz 5x5 y PDF dibujado con jsPDF.
import { jsPDF } from 'jspdf';

export const LETRAS = ['B', 'I', 'N', 'G', 'O'] as const;

export type Celda = number | string | null | undefined;

export interface Tabla {
  _id?: string;
  serial: string;
  matrix?: Celda[] | Celda[][];
  won?: boolean;
}

/** Normaliza la matriz a 5x5 (acepta 2D o plana). */
export const toMatrix = (matrix: Tabla['matrix']): Celda[][] => {
  const mat = Array.isArray(matrix) ? matrix : [];
  if (!mat.length) return Array.from({ length: 5 }, () => Array<Celda>(5).fill(''));
  if (!Array.isArray(mat[0])) {
    const flat = (mat as Celda[]).slice(0, 25);
    return Array.from({ length: 5 }, (_, r) => flat.slice(r * 5, r * 5 + 5));
  }
  return mat as Celda[][];
};

/** La celda central (null / 'FREE') se muestra como "LIBRE". */
export const cellText = (value: Celda): string =>
  value === null || value === undefined || value === '' || value === 'FREE'
    ? 'LIBRE'
    : String(value);

/** Genera un PDF con 2 tablas por página (sin capturas de pantalla). */
export const descargarTablasPDF = (tablas: Tabla[], titulo: string, archivo: string): void => {
  const pdf = new jsPDF({ unit: 'mm', format: 'a4' });
  const pageW = pdf.internal.pageSize.getWidth();
  const cell = 22;
  const left = (pageW - cell * 5) / 2;

  tablas.forEach((tabla, i) => {
    const slot = i % 2;
    if (i > 0 && slot === 0) pdf.addPage();
    let y = 15 + slot * 140;

    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(12);
    pdf.text(titulo, pageW / 2, y, { align: 'center' });
    y += 7;
    pdf.setFontSize(11);
    pdf.text(`Serial: ${tabla.serial || ''}`, pageW / 2, y, { align: 'center' });
    y += 6;

    LETRAS.forEach((l, c) => {
      pdf.setFillColor(37, 99, 235);
      pdf.rect(left + c * cell, y, cell, 10, 'F');
      pdf.setTextColor(255, 255, 255);
      pdf.setFontSize(14);
      pdf.text(l, left + c * cell + cell / 2, y + 7, { align: 'center' });
    });
    pdf.setTextColor(0, 0, 0);
    y += 10;

    toMatrix(tabla.matrix).forEach((row, r) => {
      row.forEach((value, c) => {
        const x = left + c * cell;
        const top = y + r * cell;
        pdf.rect(x, top, cell, cell);
        const texto = cellText(value);
        const libre = texto === 'LIBRE';
        pdf.setFont('helvetica', 'bold');
        pdf.setFontSize(libre ? 9 : 16);
        pdf.text(texto, x + cell / 2, top + cell / 2 + (libre ? 1.5 : 2.5), { align: 'center' });
      });
    });
  });

  pdf.save(archivo);
};

/** Precio según la cantidad de tablas: 5 por $10, 2 por $5, 1 por $3. */
export const calcularTotal = (numTablas: number): number => {
  const resto = numTablas % 5;
  return Math.floor(numTablas / 5) * 10 + Math.floor(resto / 2) * 5 + (resto % 2) * 3;
};
