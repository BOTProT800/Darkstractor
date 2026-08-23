# Darkstractor

Herramienta gráfica y escrita en Python para explorar, extraer y administrar modificaciones de **Darksiders II Deathinitive Edition** en Windows.

La extracción y el repaquetado se realizan en carpetas independientes. La instalación de un mod solo ocurre después de una confirmación explícita, con el juego cerrado, un respaldo automático y comprobaciones SHA-256.

## Funciones

- Lee `manifest.bin` y maneja los offsets de 64 bits de Deathinitive.
- Indexa `media.upak` y `maps.upak` conservando nombres y carpetas.
- Lee la tabla interna de los OBP Deathinitive y separa sus recursos con nombres y tipos.
- Extrae directamente DDS, O3D, modelos `.2`, BMAT, ANM, BNK, SMF, LOC, fuentes y formatos auxiliares.
- Descomprime automáticamente los recursos `.zgfx` de Scaleform a `.gfx`.
- Cuando una variante no tiene tabla utilizable, recupera el `.bod` completo mediante zlib.
- Recupera los streams zlib de `anim_streams.upak` sin depender de Offzip.
- Extrae los paquetes Wwise AKPK (`core.pck`, `en.pck`, `es.pck`) a `.wem`, conservando sus IDs e idioma.
- Copia los vídeos `.bik`, subtítulos y archivos auxiliares.
- Incluye búsqueda, selección múltiple, cancelación y políticas seguras para archivos duplicados.
- Reemplaza DDS compatibles y genera una copia UPAK completa, verificada y con los mismos offsets.
- Genera un manifiesto de seguridad que vincula cada mod con la versión exacta del UPAK fuente.
- Instala y desinstala UPAK con respaldo automático, escritura transaccional y verificación SHA-256.
- No necesita QuickBMS, Offzip ni paquetes de Python externos.

## Inicio rápido

Requiere Python 3.10 o posterior. En esta carpeta ejecuta:

```powershell
python run_darkstractor.py
```

En Windows también puedes abrir `Darkstractor.pyw` con doble clic para iniciar sin una consola adicional.

La ruta predeterminada ya apunta a:

```text
C:\Program Files (x86)\Steam\steamapps\common\Darksiders II Deathinitive Edition
```

1. Pulsa **Analizar**.
2. Elige un contenedor a la izquierda.
3. Filtra o selecciona recursos en la lista derecha.
4. Pulsa **Abrir paquete** —o haz doble clic— para ver y seleccionar sus DDS, modelos, materiales y demás archivos internos.
5. Elige la carpeta de salida y pulsa **Extraer selección**.

La opción **Separar recursos internos** extrae cada miembro con su nombre. Si se desactiva, conserva los segmentos secundarios como `.obp`.

## Reemplazar una textura DDS

1. Abre el paquete OBP que contiene la textura y extráela.
2. Edita el DDS conservando dimensiones, formato de compresión, mipmaps y tamaño exacto del archivo.
3. Regresa al paquete abierto, selecciona la textura y pulsa **Reemplazar DDS…**.
4. Elige el DDS editado y una ubicación para la nueva copia `*_mod.upak`.
5. Al terminar, acepta **Instalar ahora** o utiliza **Instalar UPAK verificado…** más tarde.

Darkstractor valida la cabecera DDS, reconstruye el zlib, comprueba que el OBP siga cabiendo en su espacio original y vuelve a leer la textura desde el UPAK generado. Junto al UPAK crea `*.upak.darkstractor.json`, que contiene los hashes del origen y del resultado. Ambos archivos deben permanecer juntos para instalarlo.

## Instalar y desinstalar con seguridad

1. Cierra `Darksiders2.exe`.
2. Pulsa **Instalar UPAK verificado…** y selecciona el `*_mod.upak` generado.
3. Darkstractor comprueba que el mod no fue alterado y que el UPAK instalado es exactamente la versión usada para crearlo.
4. Antes de reemplazarlo, guarda y verifica una copia del estado previo en `%LOCALAPPDATA%\Darkstractor\backups`.
5. Para desinstalarlo, pulsa **Restaurar respaldo**. También se verifican el archivo instalado y la copia antes de restaurar.

La escritura se hace primero en un archivo temporal dentro de la carpeta del juego y solo entonces se sustituye el UPAK. Si Windows deniega el acceso a `Program Files (x86)`, cierra Steam y abre Darkstractor como administrador. Los respaldos se conservan después de restaurar para recuperación manual.

Si Steam actualiza o modifica el UPAK, Darkstractor se niega a instalar una versión incompatible. Si otro programa cambia un mod activo, la restauración normal también se detiene para no borrar esos cambios; la línea de comandos ofrece `--force` únicamente para una recuperación deliberada.

## Línea de comandos

Inventario:

```powershell
python -m darkstractor scan
```

Extraer una pista concreta:

```powershell
python -m darkstractor extract --output .\extraccion --archive core.pck --filter 454907743.wem
```

Extraer recursos cuyo nombre contiene `death`:

```powershell
python -m darkstractor extract --output .\extraccion --archive media.upak --filter death
```

Examinar el contenido de un paquete sin extraerlo:

```powershell
python -m darkstractor members --archive media.upak --filter ui_buttons_pc
```

Extraer únicamente un recurso interno concreto:

```powershell
python -m darkstractor extract --output .\extraccion --archive media.upak --filter ui_buttons_pc --inner-filter button_caps.dds
```

Crear un UPAK modificado desde la línea de comandos:

```powershell
python -m darkstractor replace-dds `
  --archive media.upak `
  --package ui_buttons_pc `
  --member button_caps.dds `
  --replacement .\editado\button_caps.dds `
  --output .\mods\media_mod.upak
```

Instalarlo con respaldo y hashes:

```powershell
python -m darkstractor install-upak `
  --input .\mods\media_mod.upak
```

Consultar modificaciones activas y restaurar el estado anterior:

```powershell
python -m darkstractor mods
python -m darkstractor restore-upak --archive media.upak
```

Se puede añadir `--backup-dir D:\Respaldos\Darkstractor` a estos comandos para elegir otro disco. La GUI utiliza la carpeta segura predeterminada de `%LOCALAPPDATA%`.

Usa `--raw` para conservar los segmentos UPAK como `.obp` y `--overwrite` para sobrescribir archivos existentes. De forma predeterminada, los duplicados reciben un sufijo numérico.

## Qué produce cada contenedor

- `media.upak`, `maps.upak` → recursos internos nombrados; `.bod` completo si la variante carece de tabla, o `.obp` sin procesar.
- Tipo 1 → `.o3d`; tipo 2 → modelo nativo `.2`; tipo 5 → `.bmat`; tipo 6 → `.dds`.
- Tipo 8 → `.anm`; tipo 9 → `.bnk`; tipo 12 → `.gfx`; tipos 11/15/20 → `.smf`, `.sam` y `.loc`.
- `anim_streams.upak` → streams zlib numerados; se conserva la extensión identificable por su cabecera.
- `*.pck` → `.wem` y, si existen en la tabla, `.bnk`.
- `video` → copias exactas `.bik` y `.sub`.
- `otros` → copias exactas de `scripts.obsp` y los `.bin` de mundos.

## Limitaciones conocidas

- Los modelos se conservan como `.2` y los objetos como `.o3d`. No se convierten a FBX/GLB ni se reconstruyen esqueletos o pesos.
- El reemplazo DDS exige el mismo tamaño binario y la misma estructura. Todavía no reconstruye tablas u offsets para texturas de tamaño diferente.
- La copia UPAK se verifica estructuralmente, pero conviene probar cada modificación en el juego y conservar el archivo original.
- La instalación necesita espacio libre para un respaldo completo y otra copia temporal del UPAK; `media.upak` ocupa varios GB.
- No mezcla automáticamente dos UPAK modificados. Para crear un segundo cambio acumulativo, parte del UPAK actualmente instalado o restaura primero el respaldo.
- Los `.wem` permanecen en el formato original Wwise. Para interpretarlos por evento o reproducir música dinámica se recomiendan wwiser y vgmstream.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```
