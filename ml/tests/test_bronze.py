"""Pruebas del linaje del bronze: el tope SODA_MAX_ROWS deja rastro auditable (sin red)."""

import json

import pandas as pd

from vigia.datasets import DatasetSpec
from vigia.etl import bronze, silver

SPEC = DatasetSpec(
    id="homicidios",
    soda_id="m8fd-ahd9",
    name="Homicidios",
    schema_family="A",
    categoria="HOMICIDIO",
    date_format="iso",
)


def _fake_fetch(source_rows: int):
    """Sustituto de `fetch_dataset` sin red que reproduce el recorte real (`head(max_rows)`)."""

    def _fetch(soda_id, *, max_rows=None, app_token=None):
        df = pd.DataFrame({"cantidad": ["1"] * source_rows})
        if max_rows is not None:
            df = df.head(max_rows)
        return df

    return _fetch


def _meta(tmp_path) -> dict:
    return json.loads((tmp_path / "bronze" / "homicidios.meta.json").read_text(encoding="utf-8"))


def test_meta_marca_truncado_al_alcanzar_el_tope(tmp_path, monkeypatch):
    monkeypatch.setattr(bronze.settings, "data_dir", tmp_path)
    monkeypatch.setattr(bronze.settings, "soda_max_rows", 100)
    monkeypatch.setattr(bronze.settings, "soda_app_token", None)
    # Fuente con MÁS filas que el tope → la descarga se corta en 100.
    monkeypatch.setattr(bronze, "fetch_dataset", _fake_fetch(250))

    bronze.ingest_one(SPEC)

    meta = _meta(tmp_path)
    assert meta["rows"] == 100
    assert meta["row_cap"] == 100
    assert meta["capped"] is True


def test_meta_no_marca_truncado_si_la_fuente_cabe(tmp_path, monkeypatch):
    monkeypatch.setattr(bronze.settings, "data_dir", tmp_path)
    monkeypatch.setattr(bronze.settings, "soda_max_rows", 100)
    monkeypatch.setattr(bronze.settings, "soda_app_token", None)
    # Fuente con MENOS filas que el tope → completa, sin truncar.
    monkeypatch.setattr(bronze, "fetch_dataset", _fake_fetch(40))

    bronze.ingest_one(SPEC)

    meta = _meta(tmp_path)
    assert meta["rows"] == 40
    assert meta["row_cap"] == 100
    assert meta["capped"] is False


def test_meta_sin_tope_no_marca_truncado(tmp_path, monkeypatch):
    monkeypatch.setattr(bronze.settings, "data_dir", tmp_path)
    monkeypatch.setattr(bronze.settings, "soda_max_rows", None)
    monkeypatch.setattr(bronze.settings, "soda_app_token", None)
    monkeypatch.setattr(bronze, "fetch_dataset", _fake_fetch(250))

    bronze.ingest_one(SPEC)

    meta = _meta(tmp_path)
    assert meta["row_cap"] is None
    assert meta["capped"] is False


def test_bronze_cap_lee_el_flag_del_linaje(tmp_path, monkeypatch):
    monkeypatch.setattr(silver.settings, "data_dir", tmp_path)
    bdir = tmp_path / "bronze"
    bdir.mkdir()
    (bdir / "x.meta.json").write_text(
        json.dumps({"capped": True, "row_cap": 100}), encoding="utf-8"
    )
    assert silver._bronze_cap("x") == (True, 100)
    # Meta ausente → asume sin tope (no debe tumbar la construcción de silver).
    assert silver._bronze_cap("no_existe") == (False, None)


def test_bronze_ingested_at_lee_la_fecha_del_linaje(tmp_path, monkeypatch):
    """La fecha de ingesta del bronze se eleva al informe de calidad (linaje auditable desde el
    repo); meta ausente o sin la clave → None, sin tumbar la construcción."""
    monkeypatch.setattr(silver.settings, "data_dir", tmp_path)
    bdir = tmp_path / "bronze"
    bdir.mkdir()
    (bdir / "x.meta.json").write_text(
        json.dumps({"ingested_at": "2026-07-09T18:00:00+00:00"}), encoding="utf-8"
    )
    assert silver._bronze_ingested_at("x") == "2026-07-09T18:00:00+00:00"
    assert silver._bronze_ingested_at("no_existe") is None
    (bdir / "sin_fecha.meta.json").write_text(json.dumps({"rows": 5}), encoding="utf-8")
    assert silver._bronze_ingested_at("sin_fecha") is None


# ───────────── Streaming + agregación local (`fetch_streamed_aggregate`, sin red) ─────────────


class _FakeResp:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return self._rows


class _FakeSession:
    """Devuelve páginas prefabricadas en orden, imitando el avance por keyset."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        rows = self.pages[self.calls] if self.calls < len(self.pages) else []
        self.calls += 1
        return _FakeResp(rows)


class _FlakySession:
    """Corta la conexión a mitad del cuerpo UNA vez (en la 2.ª página) y luego responde bien:
    imita el `IncompleteRead` real que tumbó una ingesta de ~25 min el 2026-07-09."""

    def __init__(self, pages):
        self.pages = pages
        self.page_idx = 0
        self.fallo_pendiente = True

    def get(self, url, params=None, timeout=None):
        import requests

        if self.page_idx == 1 and self.fallo_pendiente:
            self.fallo_pendiente = False
            raise requests.exceptions.ChunkedEncodingError("corte simulado a mitad del cuerpo")
        rows = self.pages[self.page_idx] if self.page_idx < len(self.pages) else []
        self.page_idx += 1
        return _FakeResp(rows)


def test_streamed_aggregate_reintenta_la_pagina_ante_corte_de_red(monkeypatch):
    """Un error transitorio a mitad del stream NO pierde el avance: la página se re-pide (el
    keyset no avanza hasta recibirla, así que repetirla es seguro) y el agregado final queda
    completo e idéntico."""
    from vigia.ingest import soda

    pages = [
        [{"g": "a", ":id": "1"}, {"g": "b", ":id": "2"}],
        [{"g": "a", ":id": "3"}, {"g": "a", ":id": "4"}],
        [{"g": "c", ":id": "5"}],  # página corta → fin del stream
    ]
    monkeypatch.setattr(soda, "_build_session", lambda token: _FlakySession(pages))
    monkeypatch.setattr(soda.time, "sleep", lambda s: None)  # sin esperas reales en el test

    out = soda.fetch_streamed_aggregate("fake-id", ["g"], count_as="n", page_size=2)

    assert dict(zip(out["g"], out["n"], strict=True)) == {"a": 3, "b": 1, "c": 1}
    # Linaje: las filas de origen leídas quedan en attrs (el reintento NO las cuenta dos veces).
    assert out.attrs["source_rows"] == 5


def test_streamed_aggregate_colapso_intermedio_no_altera_los_conteos(monkeypatch):
    """El colapso intermedio del acumulador (acota la RAM con grupos anchos) debe producir el
    MISMO agregado que sumar todo al final: la suma de conteos por clave es asociativa."""
    from vigia.ingest import soda

    pages = [
        [{"g": "a", ":id": "1"}, {"g": "a", ":id": "2"}, {"g": "b", ":id": "3"}],
        [{"g": "b", ":id": "4"}, {"g": "a", ":id": "5"}, {"g": "c", ":id": "6"}],
        [{"g": "a", ":id": "7"}],  # página corta → fin del stream
    ]
    monkeypatch.setattr(soda, "_build_session", lambda token: _FakeSession(pages))
    # Umbral mínimo: fuerza un colapso tras CADA página (el caso más agresivo).
    monkeypatch.setattr(soda, "_ACC_COLLAPSE_ROWS", 1)

    out = soda.fetch_streamed_aggregate("fake-id", ["g"], count_as="n", page_size=3)

    assert dict(zip(out["g"], out["n"], strict=True)) == {"a": 4, "b": 2, "c": 1}
    assert out.attrs["source_rows"] == 7  # suma de los conteos ≡ filas de origen


def test_ingest_aggregated_registra_linaje_del_streaming(tmp_path, monkeypatch):
    """El meta del agregado guarda las filas de origen leídas (`source_rows`) y el `count(1)`
    del servidor (`source_count`), para conciliar la ingesta por streaming."""
    from vigia.datasets import AggregatedSpec

    monkeypatch.setattr(bronze.settings, "data_dir", tmp_path)
    monkeypatch.setattr(bronze.settings, "soda_app_token", None)

    def _fake_stream(soda_id, group_cols, *, count_as="n", where=None, app_token=None):
        df = pd.DataFrame({"g": ["a", "b"], count_as: [3, 2]})
        df.attrs["source_rows"] = 5
        return df

    monkeypatch.setattr(bronze, "fetch_streamed_aggregate", _fake_stream)
    monkeypatch.setattr(bronze, "fetch_count", lambda soda_id, **kw: 5)

    spec = AggregatedSpec(id="agg", soda_id="fake-id", name="Agregado", group_cols=("g",))
    bronze.ingest_aggregated(spec)

    meta = json.loads((tmp_path / "bronze" / "agg.meta.json").read_text(encoding="utf-8"))
    assert meta["rows"] == 2  # grupos del agregado
    assert meta["source_rows"] == 5  # filas de ORIGEN leídas por el streaming
    assert meta["source_count"] == 5  # count(1) del servidor (None si no respondiera)
