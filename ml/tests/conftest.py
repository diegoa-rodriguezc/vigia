"""Fixtures compartidos: aislamiento del artefacto de modelo.

`forecasting.train` serializa a `MODEL_PATH`, que vive en `models/` — un bind mount COMPARTIDO
con el contenedor `ml`. Sin este aislamiento, un `pytest` local reemplaza el modelo de producción
con uno entrenado sobre datos sintéticos y con la versión LOCAL de scikit-learn: si difiere de la
del contenedor, `/predict` cae en 503 "modelo incompatible" (incidente del 2026-07-03, reproducido
el 2026-07-06). El fixture redirige el artefacto a un directorio temporal por test; se copia el
real si existe para que los tests de integración (`test_hybrid`) puedan seguir cargándolo — por
eso su condición de salto (*skip*) consulta `forecasting.MODEL_PATH` (la redirigida), no `models/`
real.
La copia por test (~1 MB) cuesta milisegundos frente a los ~2 min de la suite; se prefiere a una
copia por sesión porque los tests que ENTRENAN reescriben su copia y contaminarían una compartida.
"""

import shutil

import pytest

from vigia.ml import forecasting


@pytest.fixture(autouse=True)
def _modelo_en_tmp(tmp_path, monkeypatch):
    modelo = tmp_path / "forecaster.joblib"
    meta = tmp_path / "forecaster.meta.json"
    if forecasting.MODEL_PATH.exists():
        shutil.copy2(forecasting.MODEL_PATH, modelo)
    if forecasting.META_PATH.exists():
        shutil.copy2(forecasting.META_PATH, meta)
    monkeypatch.setattr(forecasting, "MODEL_PATH", modelo)
    monkeypatch.setattr(forecasting, "META_PATH", meta)
