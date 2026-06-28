import { describe, it, expect } from "vitest";
import { paginate, pageWindow, toCSV } from "./ui";

describe("paginate", () => {
  const items = Array.from({ length: 23 }, (_, i) => i + 1);

  it("corta la primera página", () => {
    const p = paginate(items, 1, 10);
    expect(p.pageItems).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    expect(p.total).toBe(23);
    expect(p.totalPages).toBe(3);
    expect([p.from, p.to]).toEqual([1, 10]);
  });

  it("corta la última página parcial", () => {
    const p = paginate(items, 3, 10);
    expect(p.pageItems).toEqual([21, 22, 23]);
    expect([p.from, p.to]).toEqual([21, 23]);
  });

  it("clampa páginas fuera de rango", () => {
    expect(paginate(items, 99, 10).page).toBe(3); // por encima → última
    expect(paginate(items, 0, 10).page).toBe(1);  // por debajo → primera
  });

  it("maneja el conjunto vacío sin romperse", () => {
    const p = paginate([], 1, 10);
    expect(p).toMatchObject({ total: 0, totalPages: 1, from: 0, to: 0 });
    expect(p.pageItems).toEqual([]);
  });
});

describe("pageWindow", () => {
  it("sin elipsis con pocas páginas", () => {
    expect(pageWindow(1, 3)).toEqual([1, 2, 3]);
  });

  it("elipsis solo a la derecha al inicio", () => {
    expect(pageWindow(1, 20)).toEqual([1, 2, "…", 20]);
  });

  it("elipsis a ambos lados en el medio", () => {
    expect(pageWindow(10, 20)).toEqual([1, "…", 9, 10, 11, "…", 20]);
  });

  it("elipsis solo a la izquierda al final", () => {
    expect(pageWindow(20, 20)).toEqual([1, "…", 19, 20]);
  });
});

describe("toCSV", () => {
  const cols = [{ key: "municipio", label: "Municipio" }, { key: "delitos", label: "Delitos" }];

  it("emite encabezado + filas", () => {
    const csv = toCSV([{ municipio: "Cali", delitos: 42 }], cols);
    expect(csv).toBe("Municipio,Delitos\nCali,42");
  });

  it("escapa comas, comillas y saltos de línea", () => {
    const csv = toCSV([{ municipio: 'Bogotá, D.C. "centro"', delitos: 1 }], cols);
    expect(csv).toBe('Municipio,Delitos\n"Bogotá, D.C. ""centro""",1');
  });

  it("trata null/undefined como vacío", () => {
    const csv = toCSV([{ municipio: "X", delitos: null }], cols);
    expect(csv).toBe("Municipio,Delitos\nX,");
  });
});
