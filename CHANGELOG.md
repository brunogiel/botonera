# Changelog

## 1.3.1 · 2026-11-27

**Bloqueos más corto de leer, un cartel para instalar la app y un ícono nuevo.**

- **Bloqueos compacto.** Arriba, un resumen («N para hacer», «N sesiones trabadas»). Cada obstáculo y cada sesión trabada es una fila cerrada con su título en dos líneas y una sola línea de «Frena …»; un toque abre el detalle (el porqué, el link o el comando con «Copiar», el estado y los botones Listo / No puedo / Comentar, o Archivar). Se abre una fila a la vez, y la que tiene el comentario abierto no se cierra sola.
- **Bloqueos agrupa por categoría, como Decidir.** Cada grupo lleva el ícono y el color de su categoría, en el mismo orden que Decidir; las sesiones trabadas van al final y lo que no trae categoría, en «Otras». `obstaculo.py` suma `--categoria <id>` (un id de `categorias.json`); sin él, la categoría sale de `--de`.
- **Cartel para instalar la app en el inicio del celu.** La primera vez que abrís la botonera desde el navegador del celu, un cartel explica cómo instalarla: en iPhone, «Compartir» y «Agregar a inicio»; en Android, el botón «Instalar» cuando el navegador lo ofrece. No sale en compu ni si ya corre instalada, y cerrarlo lo apaga para siempre.
- **Ícono nuevo:** el cuadrado entero es un mazo de cartas.
- **La demo en línea** muestra todo esto, con datos inventados.
- Una migración nueva (`20261127000000_bm_obstaculos_categoria.sql`): la columna `categoria` de los obstáculos, un parámetro opcional más en `bm_obstaculo_publicar` y la categoría en `bm_acciones_lista`. `install.sh` la suma a `instalar.sql` y se puede repetir, así que actualizar desde la 1.3.0 es volver a correr el instalador y pegar el SQL.
- **Pruebas:** casos nuevos de Bloqueos compactos en `e2e-bloqueos.js` y `facil/tests/e2e.js`, y `e2e-instalar.js` para el cartel (`npm run e2e:todo`).

## 1.3.0 · 2026-11-26

**Dos versiones en un mismo repo: la completa con cualquier agente, y una versión fácil sin servidor.**

### Versión fácil (nueva)

- **Una página privada de Claude en lugar de tu propia web.** `skill/facil/pagina.html` es la misma web de la botonera (mismo diseño, mismos mazos, mismo menú de abajo) con la base de datos de la página de Claude en lugar de Supabase: sin cuenta, sin claves, sin PIN, sin hosting. La entrada es la cuenta de Claude de la persona; los datos viven ahí.
- **`install.sh --facil`** copia el skill (con `skill/facil/`) y nada más: no pide URL ni clave, no genera secreto, no escribe `config.js` ni SQL. Se combina con `--agente` y `--skill-dir`.
- **`armar.py --artifact datos.json salida.json`** corre las mismas validaciones que la versión completa y escribe el documento que lee la página (dibujos saneados, categoría embebida, `creada`, `estado`). Una tarjeta de opciones con un plan `aplicar` solo `comun` se acepta en esta versión. Ejemplo en `skill/ejemplo/agencia.json`.
- **`SKILL.md`** gana «Qué versión usar» (completa si existe `~/.config/botonera/env`; fácil si la sesión puede publicar páginas; si no, dice cómo instalar una) y la sección de la versión fácil. El detalle va en `skill/facil/LEEME-agente.md`.
- **`facil/`**: `derivar.py` (regenera la página desde `web/index.html`; `--check` dice si está al día), el adaptador de datos, el paso «Avisar a Claude», el confeti inline y sus pruebas (`facil/tests`: `e2e.js` y `mismo-diseno.js`).
- **Qué no tiene:** avisos al celu, ícono propio, PIN, otros agentes, obstáculos ni sesiones en vuelo.

### Versión completa

- **Tres pestañas, una vista por vez:** Sesiones · Decisiones · Bloqueos. Sesiones muestra «Trabajando ahora» (con lo que cada sesión anota con `vuelo.py`), «Hechas hoy» y el archivo. Bloqueos junta «Te esperan a vos» y lo que murió con error.
- **Tarjetas nuevas:** de revisión (un solo botón, Revisado), campo `textarea` para texto largo, `detalle` plegado, imagen a pantalla completa, «Ya no aplica» cuando una tarjeta se reemplaza (`armar.py --reemplaza <clave>#<n>[:<m>]`).
- **+info con 5 opciones** (más contexto, dibujo corto, dibujo largo, escribilo distinto, otro ejemplo) y `skill/rot.md`, la guía autocontenida para reescribir la tarjeta. **«Esto es regla»** y **«Después»** (antes «Al inbox»). Rótulos: «El agente recomienda» y «Si no decidís».
- **Obstáculos:** `obstaculo.py` publica lo que solo la persona puede hacer; `pendientes.py` lista los resueltos.
- **Un solo aviso por tanda de entradas** (ráfaga) en lugar de uno por tarjeta.
- **Bloqueo del PIN temporal y creciente:** 10 fallos seguidos bloquean 15 minutos; cada tanda nueva de 10 duplica la espera (15, 30, 60… hasta 24 h) y un ingreso correcto la pone en cero. `pin.py desbloquear` la levanta; `pin.py estado` muestra hasta cuándo. Antes quedaba bloqueada hasta desbloquear.
- **Instalador:** `--agente claude|cursor|codex|otro` (codex instala en `~/.agents/skills/botonera`), reescribe la ruta del skill en `SKILL.md` y `rot.md`, `--solo-skill` (para un bot en un servidor, sin secreto), prueba de conexión (`--sin-probar` la saltea), exige `https://` salvo localhost, avisa si faltan los CLI de Supabase o Vercel, e imprime la ruta absoluta de `instalar.sql` y el comando para copiarlo.
- **Scripts:** `maestro.py` lee, en orden, las tres variables de entorno, `BM_ENV_FILE`, `~/.config/botonera/env` y `~/.config/botonera/env-bot`, y rechaza una URL `http://` que no sea localhost. `esperar.py --una-vez` consulta una vez (sale 3 si sigue abierta). `armar.py --publicar` sale con error si el servidor rechaza. `pin.py poner` ya no acepta el PIN por argumento (solo teclado oculto). `secret-bot.py` dice dónde poner el archivo en el servidor.
- **Pruebas:** `tests/prueba_instalador.sh` y ocho e2e de la web (`npm run e2e:todo`, de a un archivo por vez).
- **Docs:** README con «Elegí tu versión», sección Seguridad (qué ve cada llave, qué sale a terceros, cómo rotar), tabla por agente y «Qué no trae»; `SKILL.md` con «Si tu agente no tiene segundo plano».
- **Queda afuera de esta versión:** crear una tarea desde el celu, dictado, inbox y lecturas. La fila «Con error» se conserva.
- Migraciones nuevas (`20261121…`); `install.sh` las suma a `instalar.sql` y se pueden repetir. Actualizar desde la 1.2.x es volver a correr el instalador y pegar el SQL.

## 1.2.1 · 2026-11-07

- **El aviso de una botonera nueva lleva su título.** Con una sola, el título del aviso es el de la botonera («Volvió: <título>» si despertó de un snooze) y abajo van la categoría y «N cards por decidir». Con varias, el aviso dice «N botoneras nuevas» (o «N botoneras volvieron» si todas despertaron) y abajo van hasta 2 títulos separados por coma, con «+N» por el resto. Los títulos se recortan a 40 letras.
- **Las categorías `privada` siguen sin nombrarse.** Una botonera de una categoría marcada `privada` en `categorias.json` no muestra su título en el aviso: cuenta en el número y el aviso dice «1 botonera nueva».
- Una migración nueva (`20261107010000_bm_avisos_titulo.sql`): la función `bm_avisos_titulos` y `bm_avisos_tick` actualizada. `install.sh` la suma a `instalar.sql`; las migraciones se pueden repetir, así que actualizar desde la 1.2.0 es volver a correr el instalador y pegar el SQL.

## 1.2.0 · 2026-11-07

- **Snooze.** En la portada de cada botonera, a la izquierda (gesto, flecha ← o el botón «Snooze»), elegís cuándo vuelve: «Hoy más tarde» (antes de las 17:00), «Mañana», «El finde» o «Próximo lunes», hasta 8 días. La botonera duerme en una fila «Snoozeadas» del home con «Despertar ahora», no se envía ni se avisa por push mientras duerme, y al despertar vuelve arriba con tus marcas. Un aviso de 5 segundos con «Deshacer» cierra el gesto. Una opción marca «vence antes» si una card vence antes de que vuelva. Todas las horas se calculan en la zona horaria de tu dispositivo.
- **Portada en forma de carpeta.** La card de contexto es una carpeta del color de su categoría, con una pestaña que dice la categoría y cuántas cards trae, y una pila de cartas que asoman por arriba (una por card, hasta 4).
- **La sesión sabe del snooze.** `esperar.py` avisa una vez por snooze (`maestro: <clave> snoozeada hasta <dd-mmm HH:MM>`, en hora local de la máquina) y la sesión lo relanza sin tocar la botonera. El tope de espera pasa a 8 días.
- Una migración nueva (`20261107…`): `snooze_hasta`, `bm_snoozear` y `bm_despertar`, y `bm_lista`, `bm_recibir`, `bm_sin_cerrar`, `bm_decidir_pin` y los dos avisos aprenden de las botoneras dormidas. `install.sh` la suma a `instalar.sql`; las migraciones se pueden repetir, así que actualizar desde la 1.1.x es volver a correr el instalador y pegar el SQL.

## 1.1.1 · 2026-11-06

- **Con cualquier agente.** El README explica cómo usar la botonera con Codex, Grok, Cursor o cualquier agente que corra Python: `--skill-dir`, el `SKILL.md` como instrucciones y `BM_SESSION_ID` para agrupar las tandas.
- La web arma el link «Abrir la conversación» solo para sesiones de la app de Claude Code; las de otros agentes se muestran sin link.
- GIF de la botonera en el celu al principio del README.

## 1.1.0 · 2026-11-06

- **Editar.** La barra de la card es «No va · Editar · Va», y la fila chica suma «+info» para comentar sin decidir. Una card sí/no puede traer `campos` (hasta 5, de tipo texto, número, fecha u opción): salen cargados con lo que propuso Claude, el que cambiás queda marcado con «Antes: X» y «Volver al original», y la respuesta vuelve como `va con cambios · título → acción · campos: id=nuevo (antes viejo)`. Si cambiás un valor, salís con ‹ Volver y decidís Va, el cambio viaja igual y la card muestra «N cambios pendientes». En las cards de una opción o varias, «Editar» permite elegir y escribir qué cambia. Cmd/Ctrl+Enter equivale a «Listo» en cualquier hoja.
- **Retomar sin la sesión viva.** Cada card puede traer `aplicar`, el plan de cada respuesta posible (≤40 palabras); `armar.py` avisa cuando falta. `retomar.py <clave>` lee la respuesta y esos planes con `bm_retomar` y arma un brief que cualquier sesión nueva puede aplicar. `colgadas.py` suma «plan aplicar N/M» a cada tanda decidida y el flag `--archivar`.
- **Fila «Con error».** Arriba del home aparece lo que murió sin avisar (una tarea programada que falló, una tanda archivada con una respuesta sin aplicar) hasta que tocás «Visto». Se publica con `errores.py` (`publicar`, `desde-runs`, `--seco`).
- **Contador en el home.** Cada fila de categoría dice cuántos mazos y cuántas cards tiene («2 mazos · 5 cards»).
- **Rol de bot.** `secret-bot.py` genera un secreto aparte para agentes que no son tu sesión de Claude Code. Solo sirve con claves y `session_id` que empiezan con `bot-`: no ve las demás tandas, ni el PIN, ni publica errores. `maestro.py` también lee la config de las variables de entorno `SUPABASE_URL`, `SUPABASE_ANON_KEY` y `BM_SECRET`.
- Dos migraciones nuevas (`20261106…`); `install.sh` las suma a `instalar.sql`. Las migraciones se pueden repetir, así que actualizar desde la 1.0.x es volver a correr el instalador y pegar el SQL.
- `tests/e2e-editar.js`: 23 casos de la web con Playwright, sin Supabase. `tests/prueba_local.py` suma los chequeos de campos, retomar, errores y rol de bot.

## 1.0.0 · 2026-11-05

Primera versión pública.

- `/botonera` para Claude Code: junta las decisiones pendientes, las arma como cards con recomendación, contexto e impacto, y las publica en tu botonera.
- Web para decidir en swipe desde el celu: entra con PIN de 4 dígitos, se instala como app, tres tipos de card (sí/no, una opción, varias), comentario por card y comentario final del envío.
- La respuesta vuelve sola a la sesión que preguntó (`esperar.py`), y `marcar.py` cierra el loop: la web muestra qué se aplicó.
- Avisos push en el celu cuando llega una botonera nueva y cuando una card vence hoy o mañana, con silencio de 22 a 8 en tu zona horaria. Los avisos llevan solo conteos y nombres de categoría.
- Categorías del home editables en `categorias.json`; las marcadas `privada` no se nombran en los avisos.
- Una sola migración SQL para tu propio proyecto Supabase, con todo detrás de funciones: la clave pública sola no lee nada.
- `install.sh`: copia el skill, guarda tu config local y te deja el SQL listo para pegar. `tests/prueba_local.py` prueba el loop entero contra un Supabase local.
