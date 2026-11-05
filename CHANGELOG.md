# Changelog

## 1.0.0 · 2026-11-05

Primera versión pública.

- `/botonera` para Claude Code: junta las decisiones pendientes, las arma como cards con recomendación, contexto e impacto, y las publica en tu botonera.
- Web para decidir en swipe desde el celu: entra con PIN de 4 dígitos, se instala como app, tres tipos de card (sí/no, una opción, varias), comentario por card y comentario final del envío.
- La respuesta vuelve sola a la sesión que preguntó (`esperar.py`), y `marcar.py` cierra el loop: la web muestra qué se aplicó.
- Avisos push en el celu cuando llega una botonera nueva y cuando una card vence hoy o mañana, con silencio de 22 a 8 en tu zona horaria. Los avisos llevan solo conteos y nombres de categoría.
- Categorías del home editables en `categorias.json`; las marcadas `privada` no se nombran en los avisos.
- Una sola migración SQL para tu propio proyecto Supabase, con todo detrás de funciones: la clave pública sola no lee nada.
- `install.sh`: copia el skill, guarda tu config local y te deja el SQL listo para pegar. `tests/prueba_local.py` prueba el loop entero contra un Supabase local.
