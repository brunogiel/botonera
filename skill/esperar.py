#!/usr/bin/env python3
"""Espera en segundo plano la respuesta de una botonera publicada en la botonera.

Uso:
  python3 esperar.py <clave> [--cada 15]

Lo lanza la sesión de Claude con Bash `run_in_background`. Cuando el proceso termina, la sesión
se despierta y lee lo que imprimió, así que la última salida tiene que bastarse sola:
  - recibida            -> imprime EXACTAMENTE la respuesta (ya empieza con
                           `/botonera respuesta · <clave>`) y sale 0
  - respondida_en_chat / aplicada -> aviso de que no queda nada por aplicar, sale 0
  - no_existe           -> aviso, sale 1
  - abierta             -> duerme N segundos y vuelve a preguntar
Un corte de red o un 5xx no matan la espera: reintenta con el mismo intervalo. Un 4xx (salvo 408 y 429)
3 veces seguidas sí: imprime `maestro: esperar.py se rindió: <motivo>` y sale 1. Tope de 7 días.
Si la respuesta es una re-entrega (el esperar anterior murió después de recibirla), avisa antes.
"""
import sys
import time

import maestro

TOPE_SEGUNDOS = 7 * 24 * 3600
MAX_4XX = 3  # 4xx seguidos (salvo 408/429) antes de rendirse: no se arreglan solos


def marcar_entregada(clave):
    """Anota la clave en el estado del hook entregar.py, así no la vuelve a inyectar en el mismo turno.
    Evita que esperar.py y el hook entreguen la misma respuesta a la vez. Un error acá no rompe la espera."""
    try:
        import entregar
        estado = entregar.leer_estado()
        estado[clave] = time.time()
        entregar.guardar_estado(estado)
    except Exception:
        pass


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # la respuesta trae «·» y acentos; sin esto un stdout cp1252/ASCII revienta
    args = sys.argv[1:]
    cada = 15
    if "--cada" in args:
        i = args.index("--cada")
        try:
            cada = max(1, int(args[i + 1]))
        except (IndexError, ValueError):
            sys.exit("uso: python3 esperar.py <clave> [--cada 15]")
        del args[i:i + 2]
    if len(args) != 1:
        sys.exit("uso: python3 esperar.py <clave> [--cada 15]")
    clave = args[0]
    cfg = maestro.config()
    if not cfg:
        print("maestro: sin config (~/.config/botonera/env), no puedo esperar la respuesta")
        sys.exit(1)
    inicio = time.time()
    seguidos_4xx = 0
    while time.time() - inicio < TOPE_SEGUNDOS:
        try:
            res = maestro.rpc("bm_recibir", {"p_secret": cfg["BM_SECRET"], "p_clave": clave})
        except maestro.ErrorMaestro as ex:
            if ex.codigo and 400 <= ex.codigo < 500 and ex.codigo not in (408, 429):
                seguidos_4xx += 1
                if seguidos_4xx >= MAX_4XX:
                    print(f"maestro: esperar.py se rindió: {ex}", flush=True)
                    sys.exit(1)
            else:
                seguidos_4xx = 0
            print(f"maestro: reintento ({ex})", file=sys.stderr, flush=True)
            time.sleep(cada)
            continue
        seguidos_4xx = 0
        res = res if isinstance(res, dict) else {}
        estado = res.get("estado")
        if estado == "recibida" and res.get("respuesta_texto") is not None:
            if res.get("reentrega"):
                print(f"maestro: REENTREGA de {clave}. Antes de aplicar, chequeá si ya lo aplicaste en esta sesión.", flush=True)
            print(res["respuesta_texto"], flush=True)
            marcar_entregada(clave)
            return
        if estado in ("respondida_en_chat", "aplicada"):
            print(f"maestro: {clave} ya se resolvió ({estado}), nada que aplicar")
            return
        if estado == "no_existe":
            print(f"maestro: {clave} no existe en la botonera")
            sys.exit(1)
        time.sleep(cada)  # abierta (o recibida sin texto todavía)
    print(f"maestro: {clave} sin respuesta tras 7 días, dejo de esperar")


if __name__ == "__main__":
    main()
