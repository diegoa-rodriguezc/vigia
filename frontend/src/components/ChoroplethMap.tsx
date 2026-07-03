import { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, GeoJSON } from "react-leaflet";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import type { Layer, LeafletMouseEvent, PathOptions, Path } from "leaflet";
import type { DepartamentoResumen } from "../api";

// Propiedades del GeoJSON estático de departamentos (código DANE en `DPTO`).
interface DptoProps { DPTO: string; NOMBRE_DPT?: string }
// Las props del GeoJSON genérico se acotan a `DptoProps` en un único punto.
const propsOf = (f?: Feature<Geometry>): DptoProps => (f?.properties ?? {}) as DptoProps;

// Rampa secuencial (ámbar → rojo profundo) sobre basemap oscuro.
const RAMP = ["#1e3a5f", "#fde68a", "#fbbf24", "#fb923c", "#f97316", "#dc2626", "#991b1b"];
const NO_DATA = "#243049";

// Umbrales por cuantiles: reparte los departamentos en clases de igual tamaño,
// más robusto frente a outliers (Bogotá/Antioquia) que un corte lineal.
function quantileBreaks(values: number[], n: number): number[] {
  const v = [...values].sort((a, b) => a - b);
  const breaks: number[] = [];
  for (let i = 1; i < n; i++) {
    const pos = (v.length - 1) * (i / n);
    const lo = Math.floor(pos);
    breaks.push(v[lo] + (v[Math.ceil(pos)] - v[lo]) * (pos - lo));
  }
  return breaks;
}

interface Props {
  departamentos: DepartamentoResumen[];
  // Clic en un departamento (para cargar sus señales de prensa en Panorama).
  onSelectDepto?: (cod: string, nombre: string) => void;
  selectedCod?: string; // departamento resaltado (el seleccionado)
}

export default function ChoroplethMap({ departamentos, onSelectDepto, selectedCod }: Props) {
  const [geo, setGeo] = useState<FeatureCollection | null>(null);

  useEffect(() => {
    // Límites derivados del MGN (DANE), simplificados para web; código DANE en DPTO.
    // Procedencia y atribución: docs/DATASETS.md -> Recursos complementarios.
    fetch("/colombia-departamentos.json")
      .then((r) => r.json())
      .then((j: FeatureCollection) => setGeo(j))
      .catch(() => setGeo(null));
  }, []);

  // Índice cod_departamento → datos, y nombre/ranking para el tooltip.
  const byCod = useMemo(() => {
    const m = new Map<string, DepartamentoResumen & { rank: number }>();
    [...departamentos]
      .sort((a, b) => b.total_delitos - a.total_delitos)
      .forEach((d, i) => m.set(d.cod_departamento, { ...d, rank: i + 1 }));
    return m;
  }, [departamentos]);

  const breaks = useMemo(
    () => quantileBreaks(departamentos.map((d) => d.total_delitos), RAMP.length),
    [departamentos],
  );

  const colorFor = (total: number | undefined): string => {
    if (total == null) return NO_DATA;
    let i = 0;
    while (i < breaks.length && total > breaks[i]) i++;
    return RAMP[i];
  };

  const style = (feature?: Feature<Geometry>): PathOptions => {
    const cod = propsOf(feature).DPTO;
    const d = byCod.get(cod);
    const isSel = selectedCod != null && cod === selectedCod;
    return {
      fillColor: colorFor(d?.total_delitos),
      weight: isSel ? 3 : 1,
      color: isSel ? "#38bdf8" : "#0b1120",
      fillOpacity: isSel ? 0.95 : 0.82,
    };
  };

  const onEachFeature = (feature: Feature<Geometry>, layer: Layer) => {
    const p = propsOf(feature);
    const d = byCod.get(p.DPTO);
    const nombre = d?.departamento ?? p.NOMBRE_DPT ?? "";
    const cuerpo = d
      ? `<b>${nombre}</b><br/>${d.total_delitos.toLocaleString("es-CO")} delitos<br/>` +
        `${d.municipios} ${d.municipios === 1 ? "municipio" : "municipios"} · ` +
        `#${d.rank} a nivel nacional` +
        (onSelectDepto ? `<br/><i>clic: señales de prensa</i>` : "")
      : `<b>${nombre}</b><br/><i>sin datos</i>`;
    layer.bindTooltip(cuerpo, { sticky: true });
    layer.on({
      mouseover: (e: LeafletMouseEvent) => (e.target as Path).setStyle({ weight: 2.5, color: "#e2e8f0", fillOpacity: 0.95 }),
      mouseout: (e: LeafletMouseEvent) => (e.target as Path).setStyle(style(feature)),
      click: () => onSelectDepto?.(p.DPTO, nombre),
    });
  };

  // Etiquetas de la leyenda (rangos por clase).
  const legend = useMemo(() => {
    const fmt = (n: number) => Math.round(n).toLocaleString("es-CO");
    return RAMP.map((color, i) => {
      const lo = i === 0 ? 0 : Math.round(breaks[i - 1]) + 1;
      const hi = i < breaks.length ? Math.round(breaks[i]) : null;
      return { color, label: hi == null ? `> ${fmt(lo)}` : `${fmt(lo)} - ${fmt(hi)}` };
    });
  }, [breaks]);

  return (
    <>
      <MapContainer center={[4.6, -73.5]} zoom={5} scrollWheelZoom={false} style={{ background: "#0b1120" }}>
        <TileLayer
          attribution='&copy; OpenStreetMap, &copy; CARTO'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />
        {geo && byCod.size > 0 && (
          <GeoJSON key={`${byCod.size}-${selectedCod ?? ""}`} data={geo} style={style} onEachFeature={onEachFeature} />
        )}
      </MapContainer>
      <div className="legend">
        <span className="muted">Delitos por departamento:</span>
        {legend.map((l) => (
          <span key={l.color}><span className="dot" style={{ background: l.color }} />{l.label}</span>
        ))}
      </div>
    </>
  );
}
