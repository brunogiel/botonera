#!/usr/bin/env python3
"""PIN de la botonera: ponerlo, desbloquearla y ver cómo está.

Uso:
  python3 pin.py poner            # pide el PIN dos veces (getpass); 4 dígitos
  python3 pin.py poner 1234       # sin terminal interactiva
  python3 pin.py desbloquear      # tras 10 fallos seguidos la página queda bloqueada
  python3 pin.py estado           # puesto / fallos / bloqueado / sesiones, y una línea de avisos

Poner un PIN nuevo cierra todas las sesiones abiertas. Nunca se imprime el PIN.
"""
import getpass
import re
import sys

import maestro

USO = "uso: python3 pin.py poner [PIN] | desbloquear | estado"


def pedir_pin():
    a = getpass.getpass("PIN nuevo (4 dígitos): ")
    b = getpass.getpass("Repetilo: ")
    if a != b:
        sys.exit("pin: no coinciden, no se cambió nada")
    return a


def llamar(nombre, extra=None):
    cfg = maestro.config()
    if not cfg:
        print("maestro: sin config (~/.config/botonera/env)", file=sys.stderr)
        sys.exit(1)
    body = {"p_secret": cfg["BM_SECRET"]}
    body.update(extra or {})
    try:
        return maestro.rpc(nombre, body)
    except maestro.ErrorMaestro as ex:
        print(f"maestro: falló ({ex})", file=sys.stderr)
        sys.exit(1)


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(USO)
    cmd, resto = args[0], args[1:]

    if cmd == "poner" and len(resto) <= 1:
        pin = resto[0] if resto else pedir_pin()
        if not re.fullmatch(r"[0-9]{4}", pin):
            sys.exit("pin: tiene que ser de 4 dígitos")
        res = llamar("bm_poner_pin", {"p_pin": pin})
        if res != "ok":
            print(f"pin: no se puso ({res})", file=sys.stderr)
            sys.exit(1)
        print("pin: puesto (se cerraron todas las sesiones)")
    elif cmd == "desbloquear" and not resto:
        res = llamar("bm_desbloquear")
        if res != "ok":
            print(f"pin: no se desbloqueó ({res})", file=sys.stderr)
            sys.exit(1)
        print("pin: desbloqueado")
    elif cmd == "estado" and not resto:
        e = llamar("bm_estado_pin")
        if not isinstance(e, dict):
            print(f"pin: respuesta rara ({e})", file=sys.stderr)
            sys.exit(1)
        print(f"pin: puesto={'sí' if e.get('puesto') else 'no'} fallos={e.get('fallos')} "
              f"bloqueado={'sí' if e.get('bloqueado') else 'no'} sesiones={e.get('sesiones')}")
        av = llamar("bm_estado_avisos")
        if isinstance(av, dict):
            print(f"avisos: dispositivos={av.get('dispositivos')} ultimo={av.get('ultimo') or 'nunca'} "
                  f"error={av.get('error') or 'ninguno'}")
    else:
        sys.exit(USO)


if __name__ == "__main__":
    main()
