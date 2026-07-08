# Alineación con las Hojas de Ruta Sectoriales de Datos Abiertos Estratégicos

Complemento **sectorial** de la validación contra la Hoja de Ruta **Nacional** (ver
[DATASETS.md](DATASETS.md)). Las **25 Hojas de Ruta Sectoriales** (2024-2026) fueron elaboradas por la
Dirección de Gobierno Digital de MinTIC con las entidades cabeza de cada sector, y priorizan la apertura
de datos estratégicos por sector, alineadas con el Plan Nacional de Desarrollo 2022-2026 y el Plan
Nacional de Infraestructura de Datos (PNID). Se publican como historia oficial del portal
([`6duu-4tms`](https://www.datos.gov.co/stories/s/25-Hojas-de-Ruta-Sectoriales-de-Datos-Abiertos-Est/6duu-4tms),
consultada 2026-07-06), con los PDF distribuidos por enlaces de SharePoint de MinTIC.

Para VigIA son relevantes dos sectores: **Defensa** (la Policía Nacional, origen de 18 de los 20
datasets) y **Justicia** (el eje Fiscalía).

## Sector Defensa (Policía Nacional → 18 de los 20 datasets)

La Policía Nacional pertenece al sector **Defensa** (Ministerio de Defensa Nacional). El PDF de su hoja
sectorial no es accesible de forma anónima: el enlace publicado en la historia apunta al **visor interno
de OneDrive** de MinTIC (requiere sesión), a diferencia de los demás sectores, que usan enlaces de
acceso público. La priorización de las estadísticas de criminalidad del sector queda no obstante
**verificada por la vía Nacional**: el registro **id 70** de la Hoja de Ruta Nacional (`fn2v-r4gu`),
categoría **DEFENSA**, conjunto *"Seguridad y justicia — Estadísticas de criminalidad"* (criterio: *Our
Data Index 2025*), enlaza nominalmente 4 fuentes de VigIA y recomienda **consolidar** los conjuntos por
tipo de delito — recomendación que `silver.py` ejecuta. Verificación reproducible por API en
[DATASETS.md](DATASETS.md).

## Sector Justicia (verificado contra el PDF oficial)

*Hoja de Ruta Sectorial de Datos Abiertos Estratégicos — Sector de Justicia 2024-2026* (Ministerio de
Justicia y del Derecho, 36 págs.; **copia de evidencia**:
[hoja-ruta-sectorial-justicia.pdf](hoja-ruta-sectorial-justicia.pdf), redistribuida sin modificaciones
para reproducibilidad — el enlace oficial de SharePoint puede caducar; SHA-256
`08b360251d3c8790828a87859688de8d5fc0bb0907c678e0a6330ab12cdc1b26`, 1.079.708 bytes; declarada como
material de terceros en la sección Licencia del [README](../README.md#-licencia)). Dos hallazgos verificables:

1. **Los 25 conjuntos priorizados por el sector (Tabla 3, págs. 26-27) no cubren la criminalidad.**
   Pertenecen al Ministerio de Justicia (licencias de cannabis, contratación), la Agencia Nacional de
   Defensa Jurídica del Estado (procesos y pretensiones contra el Estado), el INPEC y la USPEC
   (penitenciario) y la Superintendencia de Notariado y Registro (escrituras, folios de matrícula).
   Ninguno aplica al reto de seguridad ciudadana: el eje delictivo **no vive en el sector Justicia del
   ejecutivo** (coherente con lo hallado en la Nacional, cuya categoría *JUSTICIA Y DEL DERECHO* cubre
   registro de propiedad, no criminalidad — ver [DATASETS.md](DATASETS.md)).
2. **La propia hoja identifica el dato de la Fiscalía como estratégico… y fuera de su alcance.** En la
   sección *2.1.1.4 Índices Internacionales de Datos Abiertos* (pág. 13), los conjuntos de mayor
   puntuación (55 en sus 5 criterios) incluyen **"Fiscalidad y delincuencia"** — origen ***OurDataIndex***
   *[sic]*, entidad responsable **Fiscalía General de la Nación** — junto a *Decisiones judiciales*
   (Consejo Superior de la Judicatura). Es el **mismo criterio** (*Our Data Index*) que sustenta el
   registro id 70 de la Nacional. Sin embargo, ni la Fiscalía ni la Judicatura aparecen entre los 25
   priorizados para apertura: son **organismos autónomos**, fuera de la gobernanza del ministerio cabeza
   de sector.

**Qué significa para VigIA.** La plataforma **reutiliza exactamente el dato que la hoja sectorial
reconoce como estratégico pero no puede gobernar**: *Procesos Fiscalía V3* (`dbdv-iihs`, ~23 millones
de procesos, publicado por la Fiscalía en datos.gov.co). El eje de **Justicia** de VigIA (embudo de
judicialización, tasa por municipio) materializa el aprovechamiento de ese vacío señalado por la propia
hoja de ruta — y demuestra que el dato ya es reutilizable hoy (la ingesta por agregación local documentada
en [DATA_DICTIONARY.md](DATA_DICTIONARY.md) es reproducible sin token).

## Índice de las 25 Hojas de Ruta Sectoriales

Enlaces oficiales tal como los publica la historia de MinTIC (pueden requerir renovación si dejan
de estar vigentes):

- [Sector Agricultura](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/Ed38JV_HD5xMpk9VIDrWQKUBY1bD7UYxAsTIZAMBg9sfiQ?e=cKAZ7q)
- [Sector Ambiente y Desarrollo Sostenible](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/ETwfZBdI4_9AlUVK8EZkeT4BI_drzSl6dHC2Nvt1FrGv8A?e=VxZHcn)
- [Sector Comercio, Industria y Turismo V2.0](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/IQDJVz7DEakMRIE_GFnUxK0YAe0jHP0_-QEmnjYZ1BvyEN4?e=4C76zg)
- [Sector Ciencia, Tecnología e Innovación](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/EXHws7ntjyNEtwcnqKhtGEsBCJ5fbhKAwFXcGdi_4HVKSA?e=dFLUQY)
- [Sector Cultura](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/EZ4IGEqkB-JBg9URCJRyZAYBncvrOMoWE_vdPlx-pkZOWA?e=IyE0qt)
- [Sector del Deporte](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/Ecou3jjTy9pCiwIee6XyhyMBiDVR1EVEvsJGlevPIT_Oag?e=ngh0ry)
- [Sector Defensa](https://mintic-my.sharepoint.com/my?viewid=bd134466%2Df0aa%2D4836%2D81af%2D980ca5c66c54&FolderCTID=0x01200086B234869F6E0240BCCF05FFC133ECB4&id=%2Fpersonal%2Fdatosabiertos%5Fmintic%5Fgov%5Fco%2FDocuments%2FRegistro%20Hojas%20de%20Ruta%20Sectorial%202024%2FHoja%20de%20Ruta%20Sector%20Defensa%5Fok%2Epdf&parent=%2Fpersonal%2Fdatosabiertos%5Fmintic%5Fgov%5Fco%2FDocuments%2FRegistro%20Hojas%20de%20Ruta%20Sectorial%202024) *(visor interno — requiere sesión)*
- [Sector Educación](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/ET_fV-xp7bNGrWk7fIfz44MBdEHn-S1QDaaYWJkSdvyjaw?e=YVSmqn)
- [Sector Estadística](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/EZRk3K0qphBCgofDc2Lr1ZkBnyVTgX6D14EzaBxjU0k4Hw?e=ekjB0F)
- [Sector Función Pública](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/EZbtEQFOBO1FjnEpD5diL5UBV0YSaKBFkfm0F8fRk1uXWQ?e=cunItG)
- [Sector Hacienda](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/EREsIEnrlWxGjnHAfHaT0ewBX80dTFTYsjG723Oqa8ebCQ?e=ePJsjM)
- [Sector Igualdad y Equidad](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/EZPrlIFCYOxFp5UtNk53z74B_JxTXjTOzxzAT9tQ98C5tw?e=HivzDA)
- [Sector Interior](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/EcmBWQTEyrBGljs7kLV4hXIBAqTxv5HwG5otWTr2jkw85w?e=xh1N9m)
- [Sector Inclusión Social y Reconciliación](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/EXgkBSSx6XxJlEdB8jKQj0ABtxaA_BPq9Qr1F7prrrPsWQ?e=98OFMC)
- [Sector Inteligencia Estratégica y Contrainteligencia](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/EZqsonMLmQpCjB7uHwe_zCcBqe5VKmjmvKNNI0lqLmzRIA?e=aHDXWo)
- [Sector Justicia](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/EaUv7VqaHShEvV9JLTP_WpgBbnQ3TdhYkTCp6ACLo5c7Og?e=njrro2) — **analizada arriba**, [copia local](hoja-ruta-sectorial-justicia.pdf)
- [Sector de Minas y Energía](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/EQv0iK4cdZFKq-b7kfaPY1ABR6TsuF59hhI930Q_--94oA?e=HdguWc)
- [Sector Planeación](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/EVJWFuYFvmFEuxFh68Utb_cBsQfN5ym4ipSpqCtceBqGLg?e=NsAUHO)
- [Sector Presidencia de la República](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/IQDkJzUAt0y9QpwLzZ74BuhPAV5K8toH9IF_sHXNHDa4DZc?e=HAWXYM)
- [Sector Relaciones Exteriores](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/EfNykP7KknlDpiEa7nYX2f4BZcmBss72Nb0POTi1nod6Tw?e=oX6m8T)
- [Sector Salud](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/EXnn0GU2emtPp_q9Q2sQG2YBusPINZL6P8g0_3yPY8d-BQ?e=cio6UU)
- [Sector Trabajo](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/IQAsK5dnwgWCQIRKcgZJJq0EAbaB_IxbS66npc6KSoAYiuo?e=MCewAF)
- [Sector Tecnologías de la Información y Comunicaciones](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/IQDRrmKBFdixQ5H3OvedZR5mAf_QQZBtdZmITP_YjiG_b98?e=fvHG2r)
- [Sector Transporte](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/EQrrLkWvYE1LjQbjMMx5DyEBVXAL_A4JFc-rEv_m_eoN5g?e=XVZiQF)
- [Sector Vivienda, Ciudad y Territorio](https://mintic-my.sharepoint.com/:b:/g/personal/datosabiertos_mintic_gov_co/EbKVUxcaxa9MniqLc1UTZtMB4WRgtvrjsI0QNNSGi5PhHg?e=DMJiZm)

## Procedencia

Contenido e índice tomados de la historia oficial
[25 Hojas de Ruta Sectoriales de Datos Abiertos Estratégicos](https://www.datos.gov.co/stories/s/25-Hojas-de-Ruta-Sectoriales-de-Datos-Abiertos-Est/6duu-4tms)
(datos.gov.co, MinTIC), consultada el **2026-07-06**. El PDF del sector Justicia se redistribuye íntegro y
sin modificaciones como evidencia de la verificación (1.079.708 bytes, descargado del enlace oficial en la
misma fecha); el del sector Defensa se cita por título al requerir sesión.
