# Análisis de sensibilidad de la mezcla modelo/persistencia (_BLEND_W) — experimento de la
# Iteración 12 (docs/CRISP-ML-Q.md, bitácora). Regenera reports/blend_sweep.json.
#
# Cómo funciona: la recursión de `_walk_forward` realimenta SIEMPRE la predicción cruda del
# modelo (la mezcla se aplica solo al evaluar y al entregar), así que UN único backtest con
# _BLEND_W=1.0 entrega la predicción cruda y permite evaluar cualquier peso a posteriori
# DE FORMA EXACTA: y_w = w*cruda + (1-w)*persistencia. Con peso 0,7 debe reproducir las
# cifras de reports/model_report.json (misma semilla y entorno) — esa igualdad valida el arnés.
#
# Ejecución (DENTRO del contenedor ml, como el resto del pipeline; el código no está montado,
# por eso se pasa por la entrada estándar):
#   docker compose exec -T ml python - < ml/scripts/blend_sweep.py
#
# No entrena el modelo final ni escribe en models/ (solo lee gold y escribe el JSON).
# Duración: ~10 min (3 orígenes de backtest sobre el panel completo).
import datetime
import json
import time

import pandas as pd

from vigia.config import settings
from vigia.ml import forecasting as fc
from vigia.ml.features import LAGS, feature_columns, make_features

t0 = time.time()
series = pd.read_parquet(settings.gold_dir / "serie_mensual.parquet")
series = fc._filter_active_series(series, min_nonzero=12)
mode = "rate" if fc._has_population(series) else "count"
feats = make_features(fc._as_modeling_target(series, mode)).dropna(subset=[f"lag_{max(LAGS)}"])
cols = feature_columns(feats)
if mode == "rate":
    cols = [c for c in cols if c != "tasa_hist"]
print(f"[{time.time() - t0:.0f}s] series listas, modo={mode}, {len(cols)} features", flush=True)

fc._BLEND_W = 1.0  # y_pred del backtest = predicción CRUDA del modelo
bt = fc._walk_forward(series, cols, n_splits=3, horizon=6, mode=mode)
print(f"[{time.time() - t0:.0f}s] backtest terminado: {bt['n_origins']} orígenes", flush=True)

step = bt["step"]
yt, yp_raw, bl = bt["y_true"], bt["y_pred"], bt["baseline"]
bls, sc = bt["bl_season"], bt["scale"]
one = step == 1

resultados = []
for w in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3):
    yp = w * yp_raw + (1.0 - w) * bl
    h1 = fc._metrics_block(yt[one], yp[one], bl[one], baseline_season=bls[one], scale=sc[one])
    mp = fc._metrics_block(yt, yp, bl, baseline_season=bls, scale=sc)
    resultados.append(
        {
            "peso_modelo": w,
            "paso1": h1,
            "multipaso": mp,
            "skill_mae_1paso_vs_persistencia_pct": round(
                100 * (1 - h1["mae"] / h1["baseline_mae"]), 1
            ),
            "skill_mae_multipaso_vs_persistencia_pct": round(
                100 * (1 - mp["mae"] / mp["baseline_mae"]), 1
            ),
        }
    )
    print(
        f"w={w}: MAE1={h1['mae']:.4f} MAEmp={mp['mae']:.4f} "
        f"sMAPE1={h1['smape']:.2f} sMAPEmp={mp['smape']:.2f} "
        f"MASE1={h1['mase']:.4f} MASEmp={mp['mase']:.4f}",
        flush=True,
    )

out = {
    "experimento": "análisis de sensibilidad de _BLEND_W (Iteración 12) — backtest único "
    "con peso 1.0, re-mezcla exacta a posteriori",
    "generado": datetime.datetime.now().isoformat(timespec="seconds"),
    "n_origins": int(bt["n_origins"]),
    "horizon": int(bt["horizon"]),
    "modo": mode,
    "nota_ruido": "HGB con early_stopping multi-hilo: las cifras fluctúan ~1% entre ejecuciones; "
    "comparar w=0.7 contra reports/model_report.json valida el arnés dentro de esa banda",
    "lineas_base": {
        "persistencia_mae_1paso": resultados[0]["paso1"]["baseline_mae"],
        "persistencia_mae_multipaso": resultados[0]["multipaso"]["baseline_mae"],
        "estacional_mae_1paso": resultados[0]["paso1"].get("baseline_estacional_mae"),
        "estacional_mae_multipaso": resultados[0]["multipaso"].get("baseline_estacional_mae"),
    },
    "sensibilidad": resultados,
}
dest = settings.reports_dir / "blend_sweep.json"
dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"[{time.time() - t0:.0f}s] escrito {dest}", flush=True)
