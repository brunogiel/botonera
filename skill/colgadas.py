#!/usr/bin/env python3
"""Lista las botoneras de la botonera que no llegaron a un estado cerrado (para una limpieza periódica).

Uso:
  python3 colgadas.py

Una botonera está colgada si sigue `abierta`, `decidida`, `recibida` o `esperando`. Imprime una línea por fila:
  clave · estado · sesión · hace cuánto se creó · session_id
El script solo lista. Quien la corre decide cuál ya no está (sesión archivada o borrada) y la cierra con
`marcar.py <clave> archivada "<por qué>"`. Sale siempre 0: sin config, sin red o sin nada colgado solo lo dice.
"""
import maestro
from pendientes import hace


def main():
    cfg = maestro.config()
    if not cfg:
        print("maestro: sin config (~/.config/botonera/env), no puedo mirar colgadas")
        return
    try:
        res = maestro.rpc("bm_sin_cerrar", {"p_secret": cfg["BM_SECRET"]})
    except maestro.ErrorMaestro as ex:
        print(f"maestro: falló ({ex})")
        return
    filas = [res] if isinstance(res, dict) else (res or [])
    if not filas:
        print("maestro: nada colgado")
        return
    print(f"maestro: {len(filas)} sin cerrar")
    for f in filas:
        print(f"{f.get('clave')} · {f.get('estado')} · {f.get('sesion_titulo') or '(sin título)'} · "
              f"hace {hace(f.get('created_at'))} · {f.get('session_id') or 'sin session_id'}")


if __name__ == "__main__":
    main()
