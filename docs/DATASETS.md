# Fuentes consultadas


Fuente | URL | SODA2
---|---|---|
HOJA DE RUTA NACIONAL DE DATOS ABIERTOS ESTRATÉGICOS | https://www.datos.gov.co/Estad-sticas-Nacionales/Hoja-de-Ruta-Nacional-de-datos-abiertos-estrat-gic/fn2v-r4gu/data_preview | https://www.datos.gov.co/resource/fn2v-r4gu.json | 
HURTO A VEHÍCULOS | https://www.datos.gov.co/Seguridad-y-Defensa/HURTO-A-VEH-CULOS/csb4-y6v2 | https://www.datos.gov.co/resource/csb4-y6v2.json |
Reporte Capturas Policía Nacional | https://www.datos.gov.co/Seguridad-y-Defensa/Reporte-Capturas-Polic-a-Nacional/3jdh-nmwu/about_data | https://www.datos.gov.co/resource/3jdh-nmwu.json |
Amenazas Policía Nacional de Colombia | https://www.datos.gov.co/Seguridad-y-Defensa/Amenazas-Polic-a-Nacional-de-Colombia/meew-mguv | https://www.datos.gov.co/resource/meew-mguv.json |
Reporte Hurto por Modalidades – Policía Nacional | https://www.datos.gov.co/Seguridad-y-Defensa/Reporte-Hurto-por-Modalidades-Polic-a-Nacional/d4fr-sbn2 | https://www.datos.gov.co/resource/d4fr-sbn2.json |
Reporte Delito Violencia Intrafamiliar – Policía Nacional | https://www.datos.gov.co/Seguridad-y-Defensa/Reporte-Delito-Violencia-Intrafamiliar-Polic-a-Nac/vuyt-mqpw | https://www.datos.gov.co/resource/vuyt-mqpw.json |
Homicidio – Policía Nacional | https://www.datos.gov.co/Seguridad-y-Defensa/HOMICIDIO/m8fd-ahd9 | https://www.datos.gov.co/resource/m8fd-ahd9.json |
Catálogo Seguridad y Defensa – datos.gov.co | https://www.datos.gov.co/browse?category=Seguridad+y+Defensa |
Estadística Delictiva – Policía Nacional (portal oficial) | https://www.policia.gov.co/estadistica-delictiva |
Datos Abiertos – Fiscalía General de la Nación | https://www.fiscalia.gov.co/colombia/gestion/estadisticas/ |
Auditorías Policía Nacional | https://www.datos.gov.co/Seguridad-y-Defensa/Auditor-as-Polic-a-Nacional/yiu6-gjbe/data_preview | https://www.datos.gov.co/resource/yiu6-gjbe.json |
Demandas notificadas a la Policía Nacional | https://www.datos.gov.co/Seguridad-y-Defensa/Demandas-notificadas-a-la-Polic-a-Nacional/4uxk-dt6c/about_data | https://www.datos.gov.co/resource/4uxk-dt6c.json |
Resultados operativos realizados por la Policía Nacional en control a la explotación ilícita de yacimiento minero | https://www.datos.gov.co/Seguridad-y-Defensa/Resultados-operativos-realizados-por-la-Polic-a-Na/4y5w-y5sj/about_data | https://www.datos.gov.co/resource/4y5w-y5sj.json |
Reporte Incautación de Armas de Fuego Policía Nacional | https://www.datos.gov.co/Seguridad-y-Defensa/Reporte-Incautaci-n-de-Armas-de-Fuego-Polic-a-Naci/2iz5-9bbz/about_data | https://www.datos.gov.co/resource/2iz5-9bbz.json |
Recuperación Vehículos Policía Nacional | https://www.datos.gov.co/Seguridad-y-Defensa/Recuperaci-n-Veh-culos-Polic-a-Nacional/dhy3-732k/data_preview | https://www.datos.gov.co/resource/dhy3-732k.json |
DANE – Estadísticas Seguridad y Defensa | https://www.dane.gov.co/index.php/estadisticas-por-tema/seguridad-y-defensa |
Atlas del Crimen – uso de datos (concurso anterior) | https://herramientas.datos.gov.co/index.php/usos/atlas-del-crimen |
DIVIPOLA - Códigos cabeceras - Centros poblados | https://www.datos.gov.co/Mapas-Nacionales/DIVIPOLA-C-digos-cabeceras-Centros-poblados/xaxy-8nri/data_preview | https://www.datos.gov.co/resource/xaxy-8nri.json |
Asset Inventory | https://www.datos.gov.co/Ciencia-Tecnolog-a-e-Innovaci-n/Asset-Inventory-Public/uzcf-b9dh/data_preview | https://www.datos.gov.co/resource/uzcf-b9dh.json |

# Validación contra la Hoja de Ruta Nacional de Datos Abiertos Estratégicos

La fila *HOJA DE RUTA NACIONAL* (`fn2v-r4gu`, arriba) se consultó vía API para verificar que las fuentes
de VigIA priorizan los conjuntos estratégicos del concurso. **Resultado verificado** (2026-06):

- **Registro priorizado:** categoría **DEFENSA**, **id 70**, conjunto *"Seguridad y justicia – Estadísticas
  de criminalidad"* (entidad: Ministerio de Defensa; sistema: Observatorio de DDHH y Defensa Nacional;
  criterio: *Our Data Index 2025*; estado: APERTURADO).
- **Recomendación oficial:** `recomendaciones = "CONSOLIDAR"` → *"Existen conjuntos de datos por tipo de
  delito, se recomienda consolidar todos los delitos."* VigIA la ejecuta en `silver.py`.
- **SODA ids enlazados nominalmente en el registro id 70** (verificados uno a uno con
  `$where=enlace_portal_dato_abierto like '%<id>%'`):

  | SODA2 | Fuente | ¿Usada en VigIA? |
  |---|---|---|
  | `m8fd-ahd9` | HOMICIDIO | ✅ |
  | `7mn7-vzqp` | HURTO A RESIDENCIAS | ✅ |
  | `4v6r-wu98` | DELITOS INFORMÁTICOS | ✅ |
  | `bz43-8ahq` | DELITOS SEXUALES | ✅ |

  Las otras 12 fuentes (9 de delito + 3 de respuesta institucional) no están enlazadas una a una, pero
  pertenecen al mismo conjunto priorizado *"Estadísticas de criminalidad"*; las de delito materializan la
  recomendación de consolidar.
- **Conjunto priorizado aún NO aperturado:** id 39 (ESTADÍSTICAS, DPS) *"Seguridad y justicia – Violencia
  basada en género"* (estado NO APERTURADO, recomendación APERTURAR). VigIA aporta proxy con
  `delitos_sexuales` y `violencia_intrafamiliar`.
- **Acotación:** la categoría *JUSTICIA Y DEL DERECHO* (id 137) cubre registro de propiedad/tierras, no
  criminalidad → el núcleo del reto vive en DEFENSA id 70.

Consulta usada para reproducir la verificación:

```bash
# Registro de criminalidad priorizado (DEFENSA)
curl "https://www.datos.gov.co/resource/fn2v-r4gu.json?\$where=categoria='DEFENSA'&\$select=id,conjunto_datos_priorizados,enlace_portal_dato_abierto,recomendaciones,observaciones"
# Comprobar un SODA id concreto contra los enlaces de la Hoja de Ruta
curl "https://www.datos.gov.co/resource/fn2v-r4gu.json?\$where=enlace_portal_dato_abierto%20like%20'%25m8fd-ahd9%25'&\$select=id,categoria,conjunto_datos_priorizados"
```

Detalle narrativo en [../docs/DATA_DICTIONARY.md](../docs/DATA_DICTIONARY.md) y [../README.md](../README.md).

# Expansión desde el Asset Inventory (análisis crítico)

El **Asset Inventory** (`uzcf-b9dh`) lista ~169 datasets de la categoría *Seguridad y
Defensa*. Tras la selección por relevancia para el reto de **Seguridad Ciudadana**, compatibilidad de esquema,
cobertura/frecuencia y NO duplicación, se **incorporaron 8 fuentes nuevas** (familia A "mensual" de la
Policía Nacional, esquema idéntico a HOMICIDIO: `cod_muni` 5 díg. + `fecha_hecho` ISO + `cantidad`,
cobertura nacional, vigentes a 2026-05). Detalle y justificación de descartes en
[../docs/DATA_DICTIONARY.md](../docs/DATA_DICTIONARY.md).

## Fuentes incorporadas

Fuente | SODA id | API | Categoría
---|---|---|---
HURTO PERSONAS | 4rxi-8m8d | https://www.datos.gov.co/resource/4rxi-8m8d.json | HURTO_PERSONAS
HURTO A RESIDENCIAS | 7mn7-vzqp | https://www.datos.gov.co/resource/7mn7-vzqp.json | HURTO_RESIDENCIAS
DELITOS SEXUALES | bz43-8ahq | https://www.datos.gov.co/resource/bz43-8ahq.json | DELITOS_SEXUALES
DELITOS INFORMÁTICOS | 4v6r-wu98 | https://www.datos.gov.co/resource/4v6r-wu98.json | DELITOS_INFORMATICOS
EXTORSIÓN | q2ib-t9am | https://www.datos.gov.co/resource/q2ib-t9am.json | EXTORSION
SECUESTRO | d7zw-hpf4 | https://www.datos.gov.co/resource/d7zw-hpf4.json | SECUESTRO (extorsivo/simple)
TERRORISMO | yi5j-5fe9 | https://www.datos.gov.co/resource/yi5j-5fe9.json | TERRORISMO
TRATA DE PERSONAS | 95c7-mm6s | https://www.datos.gov.co/resource/95c7-mm6s.json | TRATA_DE_PERSONAS

## Evaluadas y descartadas (con justificación)

Fuente | SODA id | Motivo de descarte
---|---|---
Incautación de Estupefacientes (y demás droga) | kk69-w2jj | `cantidad` en unidades mixtas (kg/g/und) no sumables; es *respuesta*, no delito
Lesiones Personales / acc. tránsito | 72sg-cybi / ntej-qq7v | mezclan lesión intencional con accidente de tránsito (movilidad, no el reto)
Hurto abigeato / piratería / ent. financieras | p88b-5ac7 / sutf-7dyz / i7h7-wmjc | ya contenidos en `hurto_modalidades` (d4fr-sbn2) → doble conteo
Violencia intrafamiliar (mensual) | gepp-dxcs | duplica `vuyt-mqpw` en otra periodicidad
Terrorismo / Delitos sexuales (trimestral) | 37p5-impc / fpe5-yrmw | duplican las versiones mensuales ya incluidas
Índices/esquemas/directorios/cuadrantes/etc. | (varios) | no delictivos (transparencia administrativa, infraestructura)

