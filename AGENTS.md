# AGENTS.md

Instrucciones permanentes para agentes de IA que trabajen en este repositorio.

## Atribución de código y herramientas de terceros

Siempre que se use, integre, adapte o copie algo de procedencia externa
—herramientas, librerías, scripts, snippets de código, formatos documentados
por terceros, notas de ingeniería inversa, assets— debe quedar registrado en
`CREDITS.md`, en la raíz del repositorio.

### Qué cuenta como procedencia externa

- Herramientas ejecutadas o invocadas por el proyecto (p. ej. QuickBMS y sus scripts `.bms`).
- Código copiado o adaptado desde repos, gists, foros o wikis.
- Especificaciones de formatos binarios documentadas por otras personas
  (offsets, cabeceras, tablas de compresión), aunque la implementación sea propia.
- Assets, tablas de datos o fixtures de test que no se generaron aquí.
- Documentación consultada que determinó una decisión de diseño concreta.

### Formato de cada entrada

```markdown
### <Nombre del recurso o herramienta>

- **Autor(es):** <persona, nick o comunidad; `Desconocido — verificar` si no consta>
- **Fuente:** <URL del repo, hilo, wiki o release>
- **Licencia:** <licencia, o `Desconocida — verificar`>
- **Verificado en:** <ruta del LICENSE/COPYING, metadatos del paquete o
  cabecera del archivo donde se comprobó; `nada verificable en el repo` si no hay>
- **Redistribución:** <Sí, versionado en \<ruta\> | No — solo se detecta en el sistema
  | No — solo consultado>
- **Incorporado:** <YYYY-MM-DD>
- **Dónde se usa:** <archivos del proyecto donde vive esa influencia>
- **Uso:** <copiado tal cual | adaptado | consultado como referencia>
- **¿Modificado?:** <Sí, y en qué | No | No aplica>
- **Para qué nos sirvió:** <1-3 frases: qué problema resolvió en este proyecto>
```

`CREDITS.md` se organiza en estas secciones, en este orden:

1. `## Tools`
2. `## Adapted code`
3. `## References and documentation`
4. `## History` (recursos ya retirados del proyecto)

### Reglas

- Actualiza `CREDITS.md` en el **mismo cambio** en que entra el material
  externo, nunca "después".
- Si ya existe una entrada para esa fuente, **amplíala** en lugar de duplicarla.
- **Nunca borres entradas.** Si el código externo se elimina del proyecto,
  mueve su entrada a `## History` indicando la fecha y que ya no está en uso.
- Si no conoces el autor o la licencia, **pregunta antes de cerrar la entrada**.
  No inventes atribuciones ni asumas una licencia permisiva por defecto.
- Aplica la regla aunque el usuario no la mencione en su petición: integrar un
  script externo o portar código de otro repo ya es el disparador.
- Al terminar, informa en una línea qué entrada se añadió o modificó.
- No escribas el nombre real de una persona si en la fuente solo consta su handle.
- Todo archivo `.py` o `.pyw` nuevo empieza con las dos líneas SPDX que ya llevan los
  demás: `# SPDX-FileCopyrightText: 2026 BOTProT800` y
  `# SPDX-License-Identifier: MIT`, antes de `from __future__ import annotations`.
- Antes de versionar código o binarios de terceros, comprueba que su licencia sea
  compatible con la Licencia MIT de este proyecto (ver `LICENSE`). Las permisivas
  (MIT, BSD, ISC, Apache-2.0, CC0) lo son. **Cualquier código con copyleft (GPL,
  LGPL, AGPL, MPL) obligaría a relicenciar todo el proyecto**: consulta antes de
  añadirlo.
- Si se redistribuye un binario ajeno, su texto de licencia debe acompañarlo en el
  repositorio y hay que señalar la release exacta de origen de su código fuente.
