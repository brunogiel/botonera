---
name: botonera
description: >
  Junta las decisiones pendientes de un tema y las publica como cards para swipear en tu
  botonera (tu web propia, con PIN). Por cada decisión: qué es, el dato que la decide, qué
  recomiendo y por qué, botones que dicen la acción, un campo de comentario y el impacto de
  cada lado. Vos decidís desde el celu; la respuesta vuelve sola a esta sesión y aplico solo
  lo marcado. Usar cuando digas "/botonera", "armame las decisiones", "pasame lo que tengo
  que decidir", "botonera de esto", "qué hay que decidir acá". Sin argumento, el alcance es
  ESTA conversación.
---

# botonera

Cuando tenés varias cosas para decidir y no querés leer prosa. Yo investigo y recomiendo;
vos elegís con un swipe por card. El trabajo de pensar es mío, el de elegir es tuyo.

Los scripts viven en la carpeta de este skill. Abajo se usa `~/.claude/skills/botonera/`: si lo
instalaste en otra carpeta, usá esa ruta.

## Parámetros

- `$ARGUMENTS` = el alcance. Vacío → las decisiones abiertas de ESTA conversación.
  Con texto → ese tema, proyecto o archivo (`/botonera la migración de la base`).
- Si empieza con `respuesta ·`, no se arma nada: es la vuelta de una botonera (ver §Cuando vuelve la respuesta).

## Flujo

1. **Juntar.** Barré el alcance y listá lo que espera un sí o un no del usuario.
2. **Resolver antes de preguntar.** Cada ítem llega investigado: el dato, la fecha o el número que
   lo decide. Si todavía no se puede recomendar, no entra: va aparte, como pregunta en el chat.
   *La botonera es para elegir, no para pensar.*
3. **Filtrar.** Lo obvio y reversible se hace sin preguntar y se nombra en el chat como "ya hecho".
4. **Escribir el JSON** (forma abajo) en una carpeta temporal. Lo urgente o lo que destraba, primero.
   Si son muchas y se agrupan por tema, van en `secciones`. Cada ítem trae su contexto propio
   (`antecedentes`, `si_no_decidis`, `vence` si hay plazo): se tiene que poder decidir sin abrir esta sesión.
5. **Armar y publicar.**
   ```bash
   python3 ~/.claude/skills/botonera/armar.py --publicar <tmp>/datos.json <tmp>/botonera.html
   ```
   El script valida campos, íconos y techos de palabras. Si falla, recortá el texto y volvé a correr:
   **no subas el techo.** Exit 2 = «la clave ya está cerrada»: cambiá la `clave` y volvé a correr.
   Sin `~/.config/botonera/env` avisa «maestro: sin config»: decíselo al usuario.
   El html local es un respaldo; no hace falta mostrarlo.
6. **Esperar en segundo plano.**
   ```bash
   python3 ~/.claude/skills/botonera/esperar.py <clave>     # con Bash run_in_background
   ```
   Y quedá ociosa. Cuando el usuario decide, el script sale imprimiendo
   `/botonera respuesta · <clave> …` y eso despierta a la sesión.
   Si la espera muere (se cerró la app, se reinició la sesión), en el turno siguiente corré
   `pendientes.py --horas 0` y relanzá `esperar.py <clave>`: sale al toque si ya estaba decidida.
7. **Entregar.** En el chat, una línea: cuántas cards hay en la botonera, la más urgente y las
   preguntas que quedaron afuera.

Con 0 decisiones: una línea en el chat, sin botonera.

## La forma del JSON

```json
{
  "titulo": "De qué va la tanda", "fecha": "AAAA-MM-DD",
  "clave": "botonera-AAAA-MM-DD-slug",
  "contexto": "Una línea: qué se decide y por qué ahora.",
  "origen": {"sesion_titulo": "título de esta conversación", "skill": "botonera",
             "proyecto": "opcional, texto libre", "categoria": "id de categorias.json (opcional)"},
  "intro": [{"titulo": "opcional", "items": ["viñetas cortas con el estado general"]}],
  "secciones": [{"id": "urg", "titulo": "Urgente", "nota": "opcional"}],
  "items": [{
    "n": 1, "seccion": "urg",
    "titulo": "Qué se decide, ≤9 palabras",
    "contexto": "El dato que decide, ≤25 palabras. No repite el título.",
    "reco": "va", "reco_motivo": "Por qué, ≤15 palabras.",
    "accion_va": "La acción del botón, ≤6 palabras", "accion_no_va": "La otra, ≤6 palabras",
    "antecedentes": ["1 a 3 viñetas de ≤15 palabras: qué pasó hasta acá"],
    "si_no_decidis": "≤15 palabras: qué pasa si nadie toca nada",
    "vence": "AAAA-MM-DD (opcional)",
    "impacto": {"positivo": "qué mejora y dónde", "negativo": "qué empeora o cuesta, y dónde"},
    "campos": [{"id": "precio", "etiqueta": "Precio (ARS)", "valor": 3500, "tipo": "numero"}],
    "aplicar": {"va": "Qué hacer si va, ≤40 palabras", "no_va": "Qué hacer si no va"},
    "dibujo": {"viewBox": "0 0 240 100", "alt": "qué muestra", "svg": "… (opcional)"},
    "imagen": {"path": "png/jpg local", "alt": "qué muestra", "link": "https://… (opcional)"},
    "porque": "opcional, plegado", "si_va": "opcional", "si_no_va": "opcional",
    "fuente": "opcional", "accent": "warning | danger (opcional)", "icono": "opcional"
  }],
  "fyi": {"titulo": "Lo que no es decisión", "grupos": [{"titulo": "Tema", "items": ["…"]}]}
}
```

- **`impacto` es obligatorio, con los dos lados.** Si un lado no tiene nada, se dice («Nada afuera: …»).
- **`origen.categoria`**: en qué fila del home cae la tanda. Un id de [`categorias.json`](categorias.json)
  (editalo a gusto: `orden` sale de la posición en la lista; `privada: true` hace que los avisos no
  nombren esa categoría). Sin id, `armar.py` prueba los alias, después usa `origen.proyecto` como
  categoría propia, y si no hay nada cae en `otras`. Nunca frena el armado.
- **`campos`** (opcional, solo cards sí/no, hasta 5): los valores que propusiste, `{id, etiqueta, valor, tipo}` con
  `tipo` = `texto` | `numero` | `fecha` (AAAA-MM-DD) | `opcion` (más `opciones`: 2 a 8 textos). `id` en minúscula
  sin espacios; `etiqueta` ≤6 palabras. Editar los abre cargados y la respuesta trae los valores nuevos.
- **`aplicar`** (recomendado): el plan concreto de cada respuesta, ≤40 palabras. Claves: `va` y `no_va` en una card
  sí/no; el `id` de cada opción en una con `opciones`; `comun` para el contexto compartido (rutas, archivos). Si la
  sesión murió antes de aplicar, `retomar.py` lo usa. Sin `aplicar`, `armar.py` avisa (no frena).
- **`dibujo` solo si explica algo**: antes → después, A contra B, un flujo, una cantidad, quién depende
  de qué. Un ícono que decora es peor que nada. Clases del SVG: `a` trazo · `fa` relleno · `b` acento ·
  `t` texto · `tm` texto suave · `go`/`no` relleno verde y rojo · `sgo`/`sno` trazo verde y rojo · `box` caja.
  `armar.py` limpia el SVG y la página sale con CSP: un dibujo con handlers no corre.
- **`imagen`** cuando lo que se decide se mira (una pantalla, un diseño, un mapa). `armar.py` la achica
  y la embebe (techo 900 KB). Poné también `link` para abrirla afuera.
- **`accent`** solo con semántica: `danger` = borra, mueve plata, toca credenciales o sale a un tercero sin
  vuelta. `warning` = algo sensible.
- **`clave`** única por tanda: encabeza la respuesta para saber a qué tanda contesta.

### El tipo de card

- **Sí/no.** Abajo sale **No va · Editar · Va**. La recomendada va siempre a la derecha: **`reco` es siempre
  `va`**. Si recomendás no hacerlo, escribí el título y los botones al revés para que Va sea eso («Seguir con
  la campaña», no «Pausarla»). `armar.py` rechaza `reco: no va`. **Editar** abre la hoja de un sí con un
  cambio: con `campos`, los valores que propusiste cargados para tocar; sin ellos, solo el comentario libre.
  La fila chica de abajo trae Al final, Al inbox y +info (comentar sin decidir).
- **Una opción** (`opciones`): cuando la otra salida no es un no liso.
- **Varias** (`opciones` + `varias: true`): dos o más destinos a la vez.

```json
{"n": 1, "titulo": "Qué día sale el newsletter", "contexto": "…", "reco": "jue", "reco_motivo": "…",
 "opciones": [{"id": "lun", "etiqueta": "Los lunes"}, {"id": "jue", "etiqueta": "Los jueves"},
              {"id": "otro", "etiqueta": "Otro día", "abierta": true}],
 "impacto": {"positivo": "…", "negativo": "…"}}
```

`opciones`: 2 a 5 `{id, etiqueta, abierta?}`; `id` en minúscula sin espacios, nunca `otra`; `etiqueta`
≤6 palabras. `reco` es el `id` recomendado (con `varias`, una lista). Con `opciones` no van
`accion_va`/`accion_no_va`. `condiciones` (opcional): 1 a 3 frases de ≤8 palabras, salen como chips en Editar. En estas cards,
Editar permite elegir (o no) una opción y escribir qué se cambia; no lleva `campos`.

## Reglas de contenido

- **Lo visible de una card: ~50 palabras + el dibujo o la imagen.** Título, contexto y motivo. El resto
  (impacto, por qué, si va / si no va, fuente) va plegado en «Ver más».
- **El contexto trae el dato que decide.** Mal: "Hay que ver el mail". Bien: "El mail del 15/10 solo
  tiene el link; faltan las 3 tareas prometidas".
- **Cada botón dice la acción concreta**, no «Va / No va»: «Cerrá el PR» / «Dejalo abierto».
- **FYI no es card.** Si la recomendación es «dejar como está», no es una decisión: va a `fyi`.
- **`intro` escaneable**: viñetas cortas, no párrafos.
- **Nada viene marcado.** La recomendación se ve en el botón bordeado; la marca la pone el usuario.
- **Números reales o ninguno.** Sin emoji de adorno.

## Cuando vuelve la respuesta

`esperar.py` imprime un bloque `/botonera respuesta · <clave>` con una línea por ítem:

- `N. va|no va|sin marcar · título → acción · comentario: …`
- `N. va con cambios · título → acción [· campos: id=nuevo (antes viejo); …] [· comentario: …]`: Editar. Aplicá con
  esos valores exactos (reemplazan a los de tu plan) y con el comentario.
- `N. eligió <id> · título → etiqueta [· comentario: …]` (con varias: `eligió <id>, <id>`). `eligió otra`: no marcó ninguna y el comentario es la opción.
- `N. comentario · título · comentario: …`: comentó sin decidir. Nunca es un Va. Una orden clara se aplica;
  una pregunta se contesta en una segunda vuelta.
- `N. después · título`: no se aplica; anotalo donde el usuario guarda sus pendientes.
- `notas: …` (al final): el comentario general del envío. Se lee antes que todo.

Antes de ejecutar:

1. **Leé los comentarios primero**, y `notas:` antes que todo. Un comentario puede cambiar la acción: aplicá esa versión y decilo.
2. **Lo sin marcar no se hace**, salvo que traiga un comentario que pida una acción concreta.
3. **Si algo marcado contradice algo no marcado**, preguntá antes de aplicar.
4. Aplicá y cerrá con una línea por ítem: hecho / no hecho / por qué. Esa misma línea va al cierre:
   ```bash
   python3 ~/.claude/skills/botonera/marcar.py <clave> aplicada "<una línea por ítem, separadas por \n>"
   ```
5. **Segunda vuelta**: lo que falta decidir (sin marcar, o un comentario con una pregunta) vuelve en una
   tanda nueva con **solo esos ítems**, clave `<clave>-r2`, con la respuesta metida en su contexto.

Otros estados:

- Terminás el turno sin aplicar porque necesitás algo del usuario: `marcar.py <clave> esperando "<qué necesitás>"`.
  Cuando contesta y volvés a trabajar: `marcar.py <clave> trabajando`.
- El usuario contestó en el chat en vez de swipear: `marcar.py <clave> respondida_en_chat` y frená el `esperar.py` de esa clave.
- Una tanda cuya sesión ya no existe: `marcar.py <clave> archivada "<por qué>"`.
- `marcar.py` solo acepta transiciones válidas. «NO se marcó» = el estado no era el esperado: no lo fuerces.
- Si la salida de `esperar.py` arranca con `maestro: REENTREGA`, chequeá si ya la aplicaste antes de repetir.

## Retomar una decisión sin la sesión viva

Si `esperar.py` murió y la sesión que preguntó ya no está, la respuesta sigue en la base:

```bash
python3 ~/.claude/skills/botonera/retomar.py <clave> --tomar
```

Imprime un brief: tu respuesta, el comentario final y, por card, el plan `aplicar` de **esa** respuesta (`--tomar`
pasa la tanda a `recibida` para poder cerrarla con `marcar.py … aplicada`; `--json` es para otro script). Reglas:
el comentario manda sobre el plan; lo `sin marcar` y lo `después` no se hacen; un `comentario` sin decidir no es un
Va; `eligió otra` no tiene plan; una respuesta sin plan escrito va al inbox, no se inventa. Lo interno y reversible
se aplica; lo que sale a un tercero, borra o mueve plata necesita un Va explícito.

## Fila «Con error»

Lo que murió sin avisar se publica en el home, y queda hasta que el usuario toca «Visto»:

```bash
python3 ~/.claude/skills/botonera/errores.py publicar '{"tipo":"tarea","origen_id":"<id>","titulo":"…","motivo":"…"}'
python3 ~/.claude/skills/botonera/errores.py desde-runs <runs.json> [--horas 24] [--seco]
```

`tipo` es `tarea` o `sesion`. Repetir la lectura no duplica. `colgadas.py --archivar <clave> "<por qué>"` archiva una
tanda colgada y, si ya tenía respuesta sin aplicar, publica el error `sesion`.

## Un bot con su propio secreto

Un agente que no es tu sesión de Claude Code publica con un secreto aparte (`secret-bot.py`, ver el README). Solo
sirve para claves y `session_id` que empiezan con `bot-`: `BM_SESSION_ID=bot-<nombre>` y `clave: "bot-…"`. Su tanda
no lleva link a ninguna sesión y `colgadas.py` no la archiva. El bot no ve el PIN, ni lo sin cerrar, ni publica errores.

## Mantenimiento

- `pendientes.py [--horas N]`: lo decidido que nadie aplicó.
- `colgadas.py`: las tandas que no llegaron a un estado cerrado, con su «plan aplicar N/M».
- `pin.py poner | desbloquear | estado`: el PIN de la web (10 fallos seguidos la bloquean). Poner uno nuevo cierra todas las sesiones.
- **Red de seguridad opcional**: `entregar.py` como hook de Claude Code (`./install.sh --hook` imprime el bloque
  para `~/.claude/settings.json`). Al arrancar cada turno busca lo decidido para esta sesión y lo inyecta.
- **Cómo se apaga**: borrá `~/.config/botonera/env`. `armar.py` sigue armando el html local y avisa que no publicó.
