"""Generador de informes de seguridad municipal (IA generativa anclada a datos).

Produce un **informe ejecutivo de ~1 página** para un municipio: panorama (delitos top y
totales), alertas (anomalías recientes), proyección (pronóstico del modelo con banda) y
judicialización (embudo Fiscalía). Cubre la línea del concurso de *"generación automática de
reportes públicos"* con IA generativa.

Diseño en dos fases para que sea **auditable y testeable**:
  1. `gather_facts` recolecta los hechos REALES reutilizando los ejecutores de `rag.tools`
     (mismos datos que el agente y el tablero) → un dict de cifras.
  2. `render` arma un contexto CERRADO con esas cifras y el LLM solo REDACTA (no calcula): el
     guardarraíl anti-alucinación del RAG, llevado al informe — las cifras provienen solo de los
     datos, nunca del modelo de lenguaje.

A diferencia del agente (`rag.agent`), NO usa uso de herramientas (*tool-use*): es generación
anclada, así que funciona con CUALQUIER proveedor, incluido **Ollama local**. El informe se pide
conciso (~180 palabras) a propósito: encaja en el tope de tokens del LLM local
(`OLLAMA_NUM_PREDICT`) sin truncarse y respeta el formato de un resumen ejecutivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from vigia.logging import get_logger
from vigia.rag import tools
from vigia.rag.providers import LLMProvider, get_llm

log = get_logger(__name__)

SYSTEM_PROMPT = (
    "Eres VigIA, un analista de seguridad ciudadana. Redactas un INFORME EJECUTIVO breve para una "
    "secretaría de seguridad municipal en Colombia, en español claro y neutral. Usa ÚNICAMENTE las "
    "cifras del bloque DATOS: no inventes ni estimes números, municipios ni categorías; si un dato "
    "no está, omítelo. Estructura: (1) panorama, (2) alerta temprana, (3) proyección, (4) "
    "judicialización, y un cierre de una línea. Máximo ~180 palabras. Escribe en TEXTO PLANO "
    "(sin marcas de markdown: nada de ** ni #). Escribe las cifras con el separador de miles "
    "de Colombia (2.439.138, no 2,439,138), los decimales con coma (5,58 %, no 5.58%) y los "
    "nombres de categoría en lenguaje natural y "
    "minúsculas (hurto a personas, no HURTO_PERSONAS). Recuerda que las cifras son "
    "hechos REGISTRADOS (denuncias/capturas), sujetos a subregistro y al despliegue policial, no "
    "la criminalidad real, y que el informe apoya decisiones AGREGADAS, no la vigilancia de "
    "personas."
)


@dataclass
class BriefResult:
    cod_municipio: str
    municipio: str
    departamento: str
    generado: str
    informe: str
    datos: dict = field(default_factory=dict)


def gather_facts(cod_municipio: str) -> dict | None:
    """Recolecta los hechos reales del municipio (cifras ancladas) reutilizando `rag.tools`.

    Devuelve None si faltan los datos gold o el municipio no existe.
    """
    serie = tools._load_gold("serie_mensual")
    resumen = tools._load_gold("resumen_municipio")
    if serie is None or resumen is None:
        return None
    cod = str(cod_municipio)
    fila = resumen[resumen["cod_municipio"] == cod]
    if fila.empty:
        return None
    r = fila.iloc[0]

    sub = serie[serie["cod_municipio"] == cod]
    delitos = sub[sub["naturaleza"] == "delito"]
    top = delitos.groupby("categoria")["cantidad"].sum().sort_values(ascending=False).head(5)
    pmin = tools._periodo_str(sub["periodo"].min())
    pmax = tools._periodo_str(sub["periodo"].max())
    panorama = {
        "total_delitos": int(delitos["cantidad"].sum()),
        "total_respuestas": int(sub[sub["naturaleza"] == "respuesta"]["cantidad"].sum()),
        "periodo": f"{pmin} a {pmax}",
        "top_delitos": [{"categoria": c, "total": int(v)} for c, v in top.items()],
    }

    # Alertas, pronóstico y justicia: se reutilizan los ejecutores de `tools` (mismas cifras
    # ancladas que el agente y el tablero). El pronóstico se hace sobre el delito #1 del municipio.
    alertas = tools.execute("anomalias", {"cod_municipio": cod})
    justicia = tools.execute("embudo_justicia", {"cod_municipio": cod})
    pronostico = None
    if panorama["top_delitos"]:
        categoria_principal = panorama["top_delitos"][0]["categoria"]
        pronostico = tools.execute(
            "pronostico", {"cod_municipio": cod, "categoria": categoria_principal, "horizonte": 6}
        )

    return {
        "cod_municipio": cod,
        "municipio": str(r["municipio"]),
        "departamento": str(r["departamento"]),
        "panorama": panorama,
        "alertas": alertas if alertas.get("encontrado") else None,
        "pronostico": pronostico if (pronostico and pronostico.get("encontrado")) else None,
        "justicia": justicia if justicia.get("encontrado") else None,
    }


def build_context(facts: dict) -> str:
    """Arma el bloque DATOS (contexto cerrado) a partir de los hechos recolectados."""
    p = facts["panorama"]
    lineas = [
        f"Municipio: {facts['municipio']} ({facts['departamento']}), "
        f"código DANE {facts['cod_municipio']}.",
        f"Periodo con datos: {p['periodo']}.",
        f"Total de delitos registrados: {p['total_delitos']}. "
        f"Total de respuesta institucional (capturas/incautaciones/recuperaciones): "
        f"{p['total_respuestas']}.",
        "Delitos más frecuentes (acumulado histórico): "
        + "; ".join(f"{d['categoria']}={d['total']}" for d in p["top_delitos"]),
    ]
    al = facts.get("alertas")
    if al and al.get("anomalias"):
        recientes = "; ".join(
            f"{a['categoria']} en {a['periodo']} "
            f"(severidad {a['severidad']}, {a['cantidad']} hechos)"
            for a in al["anomalias"][:3]
        )
        lineas.append(f"Anomalías recientes (picos atípicos al alza): {recientes}.")
    else:
        lineas.append("Anomalías recientes: ninguna registrada.")
    fc = facts.get("pronostico")
    if fc and fc.get("proyeccion"):
        proy = "; ".join(
            f"{x['periodo']}: {x['prediccion']} "
            f"(rango {x['limite_inferior']}-{x['limite_superior']})"
            for x in fc["proyeccion"]
        )
        lineas.append(
            f"Pronóstico de {fc['categoria']} (banda ~{fc.get('banda_pct', 80)}%): {proy}."
        )
    ju = facts.get("justicia")
    if ju:
        lineas.append(
            f"Judicialización (Fiscalía): tasa {ju['tasa_judicializacion_pct']}% "
            f"({ju['n_judicializados']} de {ju['total_procesos']} procesos superan la indagación)."
        )
    return "\n".join(lineas)


def render(facts: dict, llm: LLMProvider | None = None) -> BriefResult:
    """Genera el informe a partir de los hechos (el LLM solo redacta el contexto cerrado)."""
    llm = llm or get_llm()
    contexto = build_context(facts)
    prompt = (
        f"DATOS (únicas cifras permitidas):\n{contexto}\n\n"
        f"Redacta el informe ejecutivo de seguridad para {facts['municipio']}."
    )
    informe = llm.generate(SYSTEM_PROMPT, prompt).strip()
    return BriefResult(
        cod_municipio=facts["cod_municipio"],
        municipio=facts["municipio"],
        departamento=facts["departamento"],
        generado=date.today().isoformat(),
        informe=informe,
        datos=facts,
    )


def generate_brief(cod_municipio: str, llm: LLMProvider | None = None) -> BriefResult | None:
    """Recolecta los hechos del municipio y genera su informe. None si no hay datos."""
    facts = gather_facts(cod_municipio)
    if facts is None:
        return None
    return render(facts, llm=llm)
