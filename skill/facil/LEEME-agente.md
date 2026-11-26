# Versión fácil: el resto de lo que tenés que saber

Complemento de la sección «La versión fácil» de `~/.claude/skills/botonera/SKILL.md`. Con la persona hablás con sus palabras: «tu página privada de Claude», «tarjetas»; nunca «Artifact», «tanda», «card», «doc» ni «db».

## Pendientes al arrancar
Al arrancar el skill, y con `/botonera pendientes`: si hay link guardado (`~/.config/botonera/facil-url`), hacé `list` de `tandas` y de `respuestas` con `ArtifactData`. Las que tienen respuesta, todavía no están en `estado: "aplicada"` y no están archivadas (`marcas/<clave>.archivada`) se avisan: «Hay N decisiones tuyas sin aplicar: …». Con `pendientes` no se arma nada nuevo.

## «+info»: `N. rot · …`
Una línea como `2. rot · título → Dibujo corto + Otro ejemplo · comentario: …` **no es un «va»**: la persona no entendió esa tarjeta. No se aplica nada de ella; lo demás de la respuesta se aplica normal. Para la tarjeta:

1. Reescribila entera con las reglas de [`rot.md`](../rot.md): un **dibujo obligatorio que explique** (antes → después, A contra B, un flujo, una cantidad contra un tope), `contexto` de 15 palabras o menos, 2 antecedentes como máximo (3 con «Dibujo largo»).
2. Mismos botones, opciones y campos, con los **mismos ids** que la original: la respuesta nueva se lee igual que la vieja.
3. Si vino un comentario, contestalo en el `contexto` o en un antecedente.
4. Publicala como tanda nueva `<clave>-r2` (si vuelve a pedir, `-r3`), con el mismo `n` que tenía: `armar.py --artifact` y `set` en `tandas/<clave>-r2`. Avisale en la misma conversación: «Te dejé esa tarjeta explicada de nuevo en tu página.»

(rot.md habla de publicar con `armar.py --publicar`: en la versión fácil eso es `--artifact` + `set`.)

## Qué no tiene esta versión
Si la persona lo pide, decíselo claro:
- PIN: no hay. El acceso es la cuenta de Claude de la persona.
- Avisos al celu: si la persona no abre la página, nadie le avisa que hay tarjetas nuevas.
- Ícono propio en el celu.
- Obstáculos, errores de tareas programadas y sesiones en vuelo: **Bloqueos** solo muestra respuestas sin novedad hace más de 24 horas.
- «Ver la botonera original» y el link para abrir una conversación.
- Otros agentes: la respuesta la lee tu sesión de Claude, nadie más.
- Aviso automático al abrir una sesión: lo pendiente se ve con `/botonera pendientes`.

**Dónde viven los datos:** en la cuenta de Claude de la persona (la página privada y su base), no en tu carpeta.

## La página
**Decidir** agrupa los mazos por categoría (`origen.categoria`; sin ninguna, «Pendientes»). **Sesiones** muestra lo ya enviado: «Mandada», «Trabajando» y «Hecha», con lo que escribas en `estado` y en `resumen`. **Bloqueos** queda vacío salvo que una respuesta lleve más de 24 horas sin novedad: ahí aparece con un botón «Archivar».

## Borrar
Pedile a Claude que borre la página de pendientes, o la persona la borra desde la galería de páginas de claude.ai. Se borra también todo lo guardado. Después borrá `~/.config/botonera/facil-url`.
