#!/usr/bin/env python3
"""Lista las botoneras decididas en la botonera que nadie aplicó todavía (red de seguridad).

Uso:
  python3 pendientes.py [--horas 2]

Una botonera cuenta como pendiente si está `decidida` o `recibida`, sin `applied_at`, y se decidió
hace más de N horas (default 2). Imprime una línea por fila:
  clave · sesión · estado · hace cuánto se decidió · session_id
Sale siempre 0: sin config, sin red o sin nada pendiente solo lo dice.
"""
import datetime
import sys

import maestro


def hace(iso):
    try:
        t = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return "?"
    seg = (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()
    if seg < 3600:
        return f"{int(seg // 60)} min"
    if seg < 86400:
        return f"{seg / 3600:.1f} h"
    return f"{seg / 86400:.1f} d"


def main():
    args = sys.argv[1:]
    horas = 2
    if "--horas" in args:
        i = args.index("--horas")
        try:
            horas = max(0, int(args[i + 1]))
        except (IndexError, ValueError):
            sys.exit("uso: python3 pendientes.py [--horas 2]")
    cfg = maestro.config()
    if not cfg:
        print("maestro: sin config (~/.config/botonera/env), no puedo mirar pendientes")
        return
    try:
        res = maestro.rpc("bm_pendientes", {"p_secret": cfg["BM_SECRET"], "p_horas": horas})
    except maestro.ErrorMaestro as ex:
        print(f"maestro: falló ({ex})")
        return
    filas = [res] if isinstance(res, dict) else (res or [])
    if not filas:
        print("maestro: nada pendiente")
        return
    print(f"maestro: {len(filas)} decidida(s) sin aplicar (hace más de {horas} h)")
    for f in filas:
        print(f"{f.get('clave')} · {f.get('sesion_titulo') or '(sin título)'} · {f.get('estado')} · "
              f"hace {hace(f.get('decided_at'))} · {f.get('session_id') or 'sin session_id'}")


if __name__ == "__main__":
    main()
