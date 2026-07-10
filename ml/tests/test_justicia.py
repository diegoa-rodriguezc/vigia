"""Pruebas de la capa "Justicia" (procesos de la Fiscalía): clasificación de etapa y gold."""

import json

import pandas as pd

from vigia.etl import justicia as J


def test_clasifica_etapa_judicializacion():
    et = pd.Series(
        ["Indagación", "Investigación", "Juicio", "Ejecución De Penas", "Sin Información"]
    )
    clases = J._clasifica_etapa(et).tolist()
    assert clases == [
        "indagacion",
        "judicializado",
        "judicializado",
        "judicializado",
        "desconocido",
    ]


def _bronze():
    # Grano año×etapa (sin mes). municipio 11001 (Bogotá): 100 indagación + 25 juicio + 25
    # ejecución → 50/150 judicializado. municipio 05001 (Medellín): 80 indagación + 20
    # investigación → 20/100. Filas basura que DEBEN descartarse: año 'Sin Información',
    # código '00000'.
    return pd.DataFrame(
        {
            "cod_dane_hecho": ["11001", "11001", "11001", "05001", "05001", "11001", "00000"],
            "a_o_hecho": ["2024", "2024", "2024", "2024", "2024", "Sin Información", "2024"],
            "etapa": [
                "Indagación",
                "Juicio",
                "Ejecución De Penas",
                "Indagación",
                "Investigación",
                "Juicio",
                "Indagación",
            ],
            "n_procesos": ["100", "25", "25", "80", "20", "999", "999"],
        }
    )


def test_build_justicia_tasa_y_descarte(tmp_path, monkeypatch):
    from vigia.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "reports_dir", tmp_path / "reports")
    settings.ensure_dirs()
    _bronze().to_parquet(settings.bronze_dir / "justicia_procesos.parquet", index=False)
    # Evita la dependencia de DIVIPOLA en el test (red/archivo): nombres oficiales simulados.
    monkeypatch.setattr(
        "vigia.etl.divipola.load_municipios",
        lambda: pd.DataFrame(
            {
                "cod_municipio": ["11001", "05001"],
                "municipio": ["BOGOTÁ, D.C.", "MEDELLÍN"],
                "departamento": ["BOGOTÁ, D.C.", "ANTIOQUIA"],
                "cod_departamento": ["11", "05"],
            }
        ),
    )

    anual = J.build_justicia()

    # La fila con año 'Sin Información' y la de código '00000' se descartaron.
    assert set(anual["cod_municipio"].unique()) == {"11001", "05001"}
    assert int(anual["n_procesos"].sum()) == 250  # 150 + 100 (sin las basura 999+999)

    resumen = pd.read_parquet(settings.gold_dir / "justicia_resumen.parquet").set_index(
        "cod_municipio"
    )
    assert resumen.loc["11001", "tasa_judicializacion_pct"] == 33.33  # (25+25)/150
    assert resumen.loc["05001", "tasa_judicializacion_pct"] == 20.0  # 20/100

    rep = json.loads((settings.reports_dir / "justicia.json").read_text(encoding="utf-8"))
    assert rep["total_procesos"] == 250
    assert rep["tasa_judicializacion_nacional_pct"] == 28.0  # (50+20)/250
    assert rep["cobertura"]["municipios"] == 2
    # Bronze ANTERIOR (sin `titulo_delito`): la salida por delito se omite y el resto no cambia.
    assert not (settings.gold_dir / "justicia_delito.parquet").exists()
    assert "tasa_por_delito" not in rep

    # Embudo por etapa CRUDA, ordenado por la cadena penal (no binario ni por volumen).
    embudo = rep["embudo_por_etapa"]
    assert [e["etapa"] for e in embudo] == [
        "Indagación",
        "Investigación",
        "Juicio",
        "Ejecución De Penas",
    ]
    assert [e["n_procesos"] for e in embudo] == [180, 20, 25, 25]
    assert embudo[0]["clase_etapa"] == "indagacion"

    # Tasa por año del hecho (evidencia del efecto cohorte, aquí un solo año).
    assert rep["tasa_por_anio"] == [
        {"anio": 2024, "procesos_etapa_conocida": 250, "tasa_judicializacion_pct": 28.0}
    ]

    # Procedencia: bronze → gold concilia y los descartes quedan desglosados por causa.
    proc = rep["procedencia"]
    assert proc["filas_agregadas_bronze"] == 7
    assert proc["procesos_bronze"] == 2248  # 250 válidos + 999 (año inválido) + 999 (sin muni)
    assert proc["procesos_gold"] == 250
    assert proc["procesos_descartados"] == {
        "sin_municipio_valido": 999,
        "anio_invalido_o_fuera_de_rango": 999,
        "conteo_no_positivo": 0,
    }
    assert proc["descartados_pct"] == 88.88
    # Sin meta del bronze (o meta anterior sin linaje del streaming) NO hay conciliación.
    assert "conciliacion_ingesta" not in proc


def _mock_divipola(monkeypatch):
    monkeypatch.setattr(
        "vigia.etl.divipola.load_municipios",
        lambda: pd.DataFrame(
            {
                "cod_municipio": ["11001", "05001"],
                "municipio": ["BOGOTÁ, D.C.", "MEDELLÍN"],
                "departamento": ["BOGOTÁ, D.C.", "ANTIOQUIA"],
                "cod_departamento": ["11", "05"],
            }
        ),
    )


def test_build_justicia_desglose_por_delito(tmp_path, monkeypatch):
    """Con `titulo_delito` en bronze: gold nacional por título, tasa por título, umbral del
    ranking y bucket 'Sin información' (título vacío) fuera del ranking."""
    from vigia.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "reports_dir", tmp_path / "reports")
    settings.ensure_dirs()
    _mock_divipola(monkeypatch)
    # Umbral bajo para poder probar el filtro con volúmenes de juguete.
    monkeypatch.setattr(J, "_MIN_PROCESOS_TASA", 100)

    pd.DataFrame(
        {
            "cod_dane_hecho": ["11001", "11001", "11001", "05001", "05001", "05001"],
            "a_o_hecho": ["2024"] * 6,
            "etapa": [
                "Indagación",
                "Juicio",
                "Ejecución De Penas",
                "Indagación",
                "Investigación",
                "Indagación",
            ],
            "n_procesos": ["100", "25", "25", "80", "20", "10"],
            "titulo_delito": [
                "Delitos Contra La Vida",
                "Delitos Contra La Vida",
                "Delitos Contra La Familia",
                "Delitos Contra La Vida",
                "Delitos Contra La Vida",
                "",  # título vacío → bucket 'Sin información', fuera del ranking
            ],
        }
    ).to_parquet(settings.bronze_dir / "justicia_procesos.parquet", index=False)
    # Meta con el linaje del streaming → el reporte debe adjuntar la conciliación de la ingesta.
    (settings.bronze_dir / "justicia_procesos.meta.json").write_text(
        json.dumps(
            {"source_rows": 260, "source_count": 262, "ingested_at": "2026-07-10T00:00:00+00:00"}
        ),
        encoding="utf-8",
    )

    J.build_justicia()

    delito = pd.read_parquet(settings.gold_dir / "justicia_delito.parquet").set_index(
        "titulo_delito"
    )
    # Vida: 100+25+80+20 = 225; judicializados = 25 (juicio) + 20 (investigación) = 45 → 20 %.
    assert delito.loc["Delitos Contra La Vida", "total_procesos"] == 225
    assert delito.loc["Delitos Contra La Vida", "tasa_judicializacion_pct"] == 20.0
    # Familia: 25 en ejecución → 100 %.
    assert delito.loc["Delitos Contra La Familia", "tasa_judicializacion_pct"] == 100.0
    # El título vacío se normalizó al bucket declarado.
    assert delito.loc["Sin información", "total_procesos"] == 10

    rep = json.loads((settings.reports_dir / "justicia.json").read_text(encoding="utf-8"))
    sec = rep["tasa_por_delito"]
    assert sec["n_titulos"] == 3
    assert sec["umbral_min_procesos_conocidos"] == 100
    # Solo Vida (225 conocidos ≥ 100) entra al ranking: Familia (25) y 'Sin información' quedan
    # fuera — el umbral evita coronar tasas extremas de bajo volumen.
    assert [r["titulo_delito"] for r in sec["menor_tasa"]] == ["Delitos Contra La Vida"]
    assert [r["titulo_delito"] for r in sec["mayor_tasa"]] == ["Delitos Contra La Vida"]
    # Los municipios NO cambian por el desglose (suma sobre el título).
    resumen = pd.read_parquet(settings.gold_dir / "justicia_resumen.parquet").set_index(
        "cod_municipio"
    )
    assert resumen.loc["11001", "tasa_judicializacion_pct"] == 33.33
    # Con meta del bronze: la conciliación de la ingesta se adjunta al bloque de procedencia
    # (las filas de origen leídas calzan con los procesos del bronze; el count(1) del servidor
    # puede diferir un poco si la fuente creció durante la ingesta).
    conc = rep["procedencia"]["conciliacion_ingesta"]
    assert conc["filas_origen_leidas"] == 260 == rep["procedencia"]["procesos_bronze"]
    assert conc["count_servidor"] == 262


def test_build_justicia_retira_gold_por_delito_rancio(tmp_path, monkeypatch):
    """Si el bronze vigente NO trae `titulo_delito`, un gold por delito de una ejecución anterior
    se retira (no debe quedar un artefacto que ya no calza con el bronze)."""
    from vigia.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "reports_dir", tmp_path / "reports")
    settings.ensure_dirs()
    _mock_divipola(monkeypatch)
    _bronze().to_parquet(settings.bronze_dir / "justicia_procesos.parquet", index=False)
    stale = settings.gold_dir / "justicia_delito.parquet"
    pd.DataFrame({"titulo_delito": ["viejo"]}).to_parquet(stale, index=False)

    J.build_justicia()

    assert not stale.exists()
