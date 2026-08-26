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

- **Autor(es):** <persona, nick o comunidad>
- **Fuente:** <URL del repo, hilo, wiki o release>
- **Licencia:** <licencia, o `desconocida`>
- **Incorporado:** <YYYY-MM-DD>
- **Uso:** <copiado tal cual | adaptado | consultado como referencia>
- **Para qué nos sirvió:** <1-3 frases: qué problema resolvió en este
  proyecto y en qué archivos vive esa influencia>
```

`CREDITS.md` se organiza en estas secciones, en este orden:

1. `## Herramientas`
2. `## Código adaptado`
3. `## Referencias y documentación`
4. `## Histórico` (recursos ya retirados del proyecto)

### Reglas

- Actualiza `CREDITS.md` en el **mismo cambio** en que entra el material
  externo, nunca "después".
- Si ya existe una entrada para esa fuente, **amplíala** en lugar de duplicarla.
- **Nunca borres entradas.** Si el código externo se elimina del proyecto,
  mueve su entrada a `## Histórico` indicando la fecha y que ya no está en uso.
- Si no conoces el autor o la licencia, **pregunta antes de cerrar la entrada**.
  No inventes atribuciones ni asumas una licencia permisiva por defecto.
- Aplica la regla aunque el usuario no la mencione en su petición: integrar un
  script externo o portar código de otro repo ya es el disparador.
- Al terminar, informa en una línea qué entrada se añadió o modificó.
