#!/usr/bin/env python3
"""Prueba de punta a punta de la botonera contra un Supabase LOCAL.

Precondiciones:
  - Docker andando y `supabase start` corrido en la carpeta del repo (aplica la migración sola).
  - Python 3.9+. Solo usa la librería estándar.

Uso:
  supabase start
  python3 tests/prueba_local.py

Qué hace (todo con un HOME temporal: no toca tu ~/.claude ni tu ~/.config):
  1. Lee la URL y la clave pública de `supabase status -o env` (o de --url / --key).
  2. Corre install.sh en el HOME temporal y aplica bootstrap.sql dentro del contenedor de la base
     (no hace falta psql: usa `docker exec`).
  3. Pone el PIN, publica tests/ejemplo.json con armar.py, entra con el PIN, decide como la web,
     recibe con esperar.py y cierra con marcar.py.
  4. Chequea los casos que tienen que fallar: PIN malo, clave pública sola, secreto malo,
     respuesta con prefijo malo.

Opciones:
  --url <url>            URL de la API (default: la de `supabase status`)
  --key <clave>          clave publishable/anon (default: la de `supabase status`)
  --workdir <dir>        carpeta que contiene supabase/ para `supabase status` (default: la del repo)
  --db-container <name>  contenedor de la base (default: supabase_db_<project_id del config.toml>)

Solo corre contra localhost: la prueba pone un PIN y publica datos de ejemplo, no es para un proyecto real.
Sale con 0 si todo pasa y con 1 si algo falla.
"""
import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent
PIN = "1234"
RESULTADOS = []  # (ok, nombre, detalle)


# ───────────────────────── utilidades ─────────────────────────

def registrar(ok, nombre, detalle=""):
    RESULTADOS.append((bool(ok), nombre, detalle))
    marca = "PASS" if ok else "FAIL"
    extra = f"  ({detalle})" if (detalle and not ok) else ""
    print(f"  [{marca}] {nombre}{extra}", flush=True)
    return bool(ok)


def correr(cmd, env=None, cwd=None, timeout=120, entrada=None):
    return subprocess.run(cmd, env=env, cwd=cwd, input=entrada, capture_output=True, text=True, timeout=timeout)


def leer_project_id():
    try:
        m = re.search(r'^project_id\s*=\s*"([^"]+)"', (REPO / "supabase" / "config.toml").read_text(encoding="utf-8"), re.M)
        return m.group(1) if m else "botonera"
    except OSError:
        return "botonera"


def supabase_status(workdir):
    if not shutil.which("supabase"):
        return None, "no encuentro el CLI de supabase en el PATH"
    cmd = ["supabase", "status", "-o", "env"]
    if workdir:
        cmd += ["--workdir", workdir]
    r = correr(cmd, cwd=str(REPO), timeout=60)
    if r.returncode != 0:
        return None, (r.stderr or r.stdout).strip().splitlines()[-1:] or "supabase status falló (¿corriste supabase start?)"
    env = {}
    for linea in r.stdout.splitlines():
        m = re.match(r'^([A-Z_0-9]+)="?(.*?)"?$', linea.strip())
        if m:
            env[m.group(1)] = m.group(2)
    return env, None


def http(metodo, url, clave_publica, cuerpo=None):
    """Devuelve (status, json_o_texto). No levanta por HTTP 4xx/5xx."""
    h = {"apikey": clave_publica, "Content-Type": "application/json"}
    if not clave_publica.startswith("sb_"):
        h["Authorization"] = f"Bearer {clave_publica}"
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, headers=h, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status, crudo = r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as ex:
        status, crudo = ex.code, ex.read().decode("utf-8", "replace")
    try:
        return status, json.loads(crudo) if crudo.strip() else None
    except ValueError:
        return status, crudo


def mensaje(cuerpo):
    return (cuerpo.get("message") if isinstance(cuerpo, dict) else str(cuerpo)) or ""


# ───────────────────────── la prueba ─────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Prueba local de la botonera contra Supabase local.")
    ap.add_argument("--url")
    ap.add_argument("--key")
    ap.add_argument("--workdir")
    ap.add_argument("--db-container")
    args = ap.parse_args()

    print("Botonera: prueba local\n")

    url, key = args.url, args.key
    if not (url and key):
        st, err = supabase_status(args.workdir)
        if st is None:
            print(f"No pude leer `supabase status`: {err}\n¿Corriste `supabase start`? También podés pasar --url y --key.")
            return 1
        url = url or st.get("API_URL")
        key = key or st.get("PUBLISHABLE_KEY") or st.get("ANON_KEY")
    if not (url and key):
        print("Falta la URL o la clave pública de Supabase.")
        return 1
    url = url.rstrip("/")
    host = urlparse(url).hostname
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(f"Me niego a correr contra {host}: esta prueba solo es para un Supabase local.")
        return 1
    contenedor = args.db_container or f"supabase_db_{leer_project_id()}"

    tmp = Path(tempfile.mkdtemp(prefix="botonera-prueba-"))
    home = tmp / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home))
    for k in ("CLAUDE_CODE_HOST_SESSION_ID", "BM_SECRET", "SUPABASE_URL", "SUPABASE_ANON_KEY"):
        env.pop(k, None)
    skill = home / ".claude" / "skills" / "botonera"
    clave = f"prueba-local-{int(time.time())}"
    web_config = REPO / "web" / "config.js"
    web_config_antes = web_config.read_text(encoding="utf-8") if web_config.exists() else None

    def rpc(nombre, cuerpo):
        return http("POST", f"{url}/rest/v1/rpc/{nombre}", key, cuerpo)

    def py(script, *a, timeout=60):
        return correr([sys.executable, str(skill / script), *a], env=env, timeout=timeout)

    try:
        # 1. instalar
        print("Instalación")
        r = correr(["bash", str(REPO / "install.sh"), "--url", url, "--key", key, "--yes",
                    "--avisar-url", f"http://supabase_kong_{leer_project_id()}:8000/functions/v1/bm-avisar"],
                   env=env, timeout=60)
        if not registrar(r.returncode == 0 and (skill / "armar.py").exists(), "install.sh copia el skill y escribe la config",
                         (r.stderr or r.stdout)[-300:]):
            return resumen()
        env_file = home / ".config" / "botonera" / "env"
        modo = oct(env_file.stat().st_mode & 0o777)
        registrar(modo == "0o600", "~/.config/botonera/env queda con permisos 600", modo)

        bootstrap = (home / ".config" / "botonera" / "bootstrap.sql").read_text(encoding="utf-8")
        r = correr(["docker", "exec", "-i", contenedor, "psql", "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-t", "-A"],
                   entrada=bootstrap, timeout=60)
        if not registrar(r.returncode == 0 and r.stdout.strip() == "ok", "bm_instalar devuelve ok",
                         (r.stderr or r.stdout).strip()[-300:] or f"¿el contenedor {contenedor} está andando?"):
            return resumen()

        # 2. PIN y publicación
        print("\nPIN y publicación")
        r = py("pin.py", "poner", PIN)
        registrar(r.returncode == 0 and "puesto" in r.stdout, "pin.py poner", r.stderr or r.stdout)
        r = py("pin.py", "estado")
        registrar(r.returncode == 0 and "puesto=sí" in r.stdout, "pin.py estado dice puesto=sí", r.stderr or r.stdout)

        datos = json.loads((REPO / "tests" / "ejemplo.json").read_text(encoding="utf-8"))
        datos = copy.deepcopy(datos)
        datos["clave"] = clave
        json_path = tmp / "tanda.json"
        json_path.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        html_path = tmp / "tanda.html"
        r = py("armar.py", "--publicar", str(json_path), str(html_path))
        registrar(r.returncode == 0 and f"maestro: creada · {clave}" in r.stdout, "armar.py --publicar crea la tanda", r.stderr or r.stdout)
        r = py("armar.py", "--publicar", str(json_path), str(html_path))
        registrar(r.returncode == 0 and f"maestro: actualizada · {clave}" in r.stdout, "republicar mientras está abierta la actualiza", r.stderr or r.stdout)

        # 3. entrar con el PIN (lo que hace la web)
        print("\nEntrada con PIN")
        st, res = rpc("bm_entrar", {"p_pin": "0000" if PIN != "0000" else "9999"})
        registrar(st == 200 and isinstance(res, dict) and res.get("ok") is False and res.get("motivo") == "pin_incorrecto",
                  "PIN incorrecto devuelve pin_incorrecto", f"{st} {res}")
        st, res = rpc("bm_entrar", {"p_pin": PIN})
        token = res.get("token") if isinstance(res, dict) else None
        if not registrar(st == 200 and token and len(token) == 64, "PIN correcto devuelve un token", f"{st} {res}"):
            return resumen()

        # 4. lista y fila con el token
        st, lista = rpc("bm_lista", {"p_token": token})
        fila = next((x for x in lista if x.get("clave") == clave), None) if isinstance(lista, list) else None
        registrar(fila is not None and fila.get("estado") == "abierta" and fila.get("n_items") == 3,
                  "bm_lista con token muestra la tanda abierta con 3 ítems", f"{st} {str(lista)[:200]}")
        st, fl = rpc("bm_fila", {"p_token": token, "p_clave": clave})
        f = fl[0] if isinstance(fl, list) and fl else (fl if isinstance(fl, dict) else {})
        registrar(st == 200 and f.get("clave") == clave and "<html" in (f.get("html") or "").lower()
                  and len((f.get("datos") or {}).get("items", [])) == 3,
                  "bm_fila con token trae el html y los datos", f"{st} {str(fl)[:200]}")
        version = f.get("updated_at")

        # 5. negativos de seguridad
        print("\nChequeos de seguridad")
        st, res = http("GET", f"{url}/rest/v1/botoneras?select=clave", key)
        registrar((st in (401, 403)) or (st == 200 and res == []), "la clave pública sola no puede leer la tabla botoneras", f"{st} {str(res)[:120]}")
        st, res = http("GET", f"{url}/rest/v1/bm_config?select=k,v", key)
        registrar((st in (401, 403)) or (st == 200 and res == []), "la clave pública sola no puede leer bm_config", f"{st} {str(res)[:120]}")
        st, res = http("POST", f"{url}/rest/v1/botoneras", key, {"clave": "x", "titulo": "x", "datos": {}, "html": "x"})
        registrar(st in (401, 403), "la clave pública sola no puede insertar en botoneras", f"{st} {str(res)[:120]}")
        st, res = rpc("bm_lista", {"p_token": "token-falso"})
        registrar(st >= 400 and "token invalido" in mensaje(res), "bm_lista con token falso se rechaza", f"{st} {res}")
        st, res = rpc("bm_recibir", {"p_secret": "secreto-falso", "p_clave": clave})
        registrar(st >= 400 and "secret invalido" in mensaje(res), "bm_recibir con secreto equivocado se rechaza", f"{st} {res}")
        st, res = rpc("bm_publicar", {"p_secret": "secreto-falso", "p_clave": "intruso", "p_session_id": None,
                                      "p_sesion_titulo": None, "p_skill": None, "p_proyecto": None, "p_titulo": "x",
                                      "p_n_items": 1, "p_datos": {}, "p_html": "<html></html>"})
        registrar(st >= 400 and "secret invalido" in mensaje(res), "bm_publicar con secreto equivocado se rechaza", f"{st} {res}")
        st, res = rpc("bm_poner_pin", {"p_secret": "secreto-falso", "p_pin": "9999"})
        registrar(st >= 400 and "secret invalido" in mensaje(res), "bm_poner_pin con secreto equivocado se rechaza", f"{st} {res}")
        st, res = rpc("bm_avisos_datos", {})
        registrar(st in (401, 403, 404), "bm_avisos_datos (solo service_role) no se puede llamar con la clave pública", f"{st} {str(res)[:120]}")
        # Las funciones internas (instalación, avisos, llaves) no se pueden llamar con la clave pública.
        internas = {
            "bm_instalar": {"p_secret_sha256": "0" * 64, "p_avisar_url": "http://x", "p_zona": "UTC", "p_contacto": "x"},
            "bm_avisos_tick": {},
            "bm_avisos_llamar": {"p_cuerpo": {}},
            "bm_avisos_guardar_vapid": {"p_publica": "a", "p_privada": "b"},
            "bm_avisos_resultado": {"p_ok": [], "p_muertos": [], "p_fallidos": [], "p_claves": [], "p_error": "x"},
            "bm_check": {"p_secret": "x"},
        }
        abiertas = [n for n, cuerpo in internas.items() if rpc(n, cuerpo)[0] not in (401, 403, 404)]
        registrar(not abiertas, "las funciones internas (instalar, avisos, llaves) no se llaman con la clave pública", ", ".join(abiertas))
        st, res = rpc("bm_decidir_pin", {"p_token": token, "p_clave": clave, "p_respuesta": "/botonera respuesta · otra-clave\n1. va"})
        registrar(st >= 400 and "respuesta invalida" in mensaje(res), "respuesta con prefijo de otra clave se rechaza", f"{st} {res}")
        st, res = rpc("bm_decidir_pin", {"p_token": token, "p_clave": clave, "p_respuesta": "1. va · sin prefijo"})
        registrar(st >= 400 and "respuesta invalida" in mensaje(res), "respuesta sin prefijo se rechaza", f"{st} {res}")
        st, res = rpc("bm_decidir_pin", {"p_token": "token-falso", "p_clave": clave, "p_respuesta": f"/botonera respuesta · {clave}\n1. va"})
        registrar(st >= 400 and "token invalido" in mensaje(res), "decidir con token falso se rechaza", f"{st} {res}")
        st, res = rpc("bm_decidir_pin", {"p_token": token, "p_clave": clave, "p_respuesta": f"/botonera respuesta · {clave}\n1. va",
                                         "p_version": "2020-01-01T00:00:00Z"})
        registrar(st == 200 and res == "cambio", "decidir contra una versión vieja devuelve cambio", f"{st} {res}")
        st, res = http("GET", f"{url}/rest/v1/rpc/bm_lista", key)
        registrar(st >= 400, "las funciones no se llaman con GET sin parámetros", f"{st}")

        # 6. decidir y recibir: esperar.py arranca ANTES de la decisión
        print("\nDecidir, recibir y marcar")
        respuesta = (f"/botonera respuesta · {clave}\n"
                     "1. va · Subir el precio de los envíos → Subir el envío\n"
                     "2. eligió mail · Elegir el canal para los avisos → Mail\n"
                     "3. no va · Archivar los pedidos viejos → Dejarlos")
        proc = subprocess.Popen([sys.executable, str(skill / "esperar.py"), clave, "--cada", "1"], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        salida = {}
        hilo = threading.Thread(target=lambda: salida.update(zip(("out", "err"), proc.communicate())), daemon=True)
        hilo.start()
        time.sleep(3)
        registrar(proc.poll() is None, "esperar.py sigue esperando mientras nadie decide")
        st, res = rpc("bm_decidir_pin", {"p_token": token, "p_clave": clave, "p_respuesta": respuesta, "p_version": version})
        registrar(st == 200 and res == "decidida", "bm_decidir_pin con token y prefijo correctos deja la tanda decidida", f"{st} {res}")
        hilo.join(timeout=30)
        if hilo.is_alive():
            proc.kill()
            hilo.join(timeout=5)
        out = (salida.get("out") or "").strip()
        registrar(not hilo.is_alive() and proc.returncode == 0 and out == respuesta,
                  "esperar.py sale con exactamente la respuesta decidida", f"rc={proc.returncode} salida={out[:200]!r} err={(salida.get('err') or '')[:200]!r}")
        st, res = rpc("bm_decidir_pin", {"p_token": token, "p_clave": clave, "p_respuesta": respuesta})
        registrar(st == 200 and res == "recibida", "decidir de nuevo no pisa una tanda ya recibida", f"{st} {res}")

        r = py("pendientes.py", "--horas", "0")
        registrar(r.returncode == 0 and clave in r.stdout, "pendientes.py lista la tanda recibida sin aplicar", r.stdout + r.stderr)

        r = py("marcar.py", clave, "aplicada", "1. hecho\\n2. hecho\\n3. no se hizo, el usuario dijo que no")
        registrar(r.returncode == 0 and "→ aplicada (antes: recibida)" in r.stdout, "marcar.py aplicada desde recibida", r.stdout + r.stderr)
        st, fl = rpc("bm_fila", {"p_token": token, "p_clave": clave})
        f = fl[0] if isinstance(fl, list) and fl else {}
        registrar(f.get("estado") == "aplicada" and "no se hizo" in (f.get("resumen_aplicado") or ""),
                  "la fila queda aplicada y con el resumen guardado", f"{st} {str(fl)[:200]}")
        r = py("marcar.py", clave, "aplicada")
        registrar(r.returncode == 1 and "NO se marcó" in r.stdout, "marcar.py aplicada dos veces se rechaza (transición inválida)", r.stdout + r.stderr)
        r = py("esperar.py", clave, "--cada", "1", timeout=30)
        registrar(r.returncode == 0 and "ya se resolvió (aplicada)" in r.stdout, "esperar.py sobre una tanda aplicada avisa que no hay nada que aplicar", r.stdout + r.stderr)
        r = py("esperar.py", "clave-que-no-existe", "--cada", "1", timeout=30)
        registrar(r.returncode == 1 and "no existe" in r.stdout, "esperar.py sobre una clave inexistente sale con 1", r.stdout + r.stderr)
        r = py("armar.py", "--publicar", str(json_path), str(html_path))
        registrar(r.returncode != 0 and "ya está" in r.stderr, "republicar una tanda ya cerrada se rechaza", r.stdout + r.stderr)
        r = py("pendientes.py", "--horas", "0")
        registrar(r.returncode == 0 and clave not in r.stdout, "pendientes.py ya no la lista", r.stdout + r.stderr)

        # 7. el PIN se bloquea tras 10 fallos y pin.py desbloquear lo abre
        print("\nBloqueo del PIN")
        for _ in range(10):
            res = rpc("bm_entrar", {"p_pin": "0000"})[1]
        registrar(isinstance(res, dict) and res.get("motivo") == "bloqueado", "10 PIN malos seguidos bloquean la entrada", str(res))
        res = rpc("bm_entrar", {"p_pin": PIN})[1]
        registrar(isinstance(res, dict) and res.get("ok") is False and res.get("motivo") == "bloqueado", "bloqueada, ni el PIN correcto entra", str(res))
        r = py("pin.py", "desbloquear")
        registrar(r.returncode == 0 and "desbloqueado" in r.stdout, "pin.py desbloquear", r.stdout + r.stderr)
        res = rpc("bm_entrar", {"p_pin": PIN})[1]
        registrar(isinstance(res, dict) and res.get("ok") is True, "después de desbloquear el PIN correcto entra", str(res))
        r = py("pin.py", "poner", "4321")
        st, res = rpc("bm_lista", {"p_token": token})
        registrar(r.returncode == 0 and st >= 400 and "token invalido" in mensaje(res), "poner un PIN nuevo cierra las sesiones viejas", f"{st} {res}")

    except Exception as ex:  # cualquier error inesperado es un FAIL, no un traceback mudo
        registrar(False, "la prueba terminó sin excepciones", f"{type(ex).__name__}: {ex}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        # install.sh reescribe web/config.js (no se versiona): lo dejamos como estaba.
        try:
            if web_config_antes is None:
                web_config.unlink(missing_ok=True)
            else:
                web_config.write_text(web_config_antes, encoding="utf-8")
        except OSError:
            pass
    return resumen()


def resumen():
    total = len(RESULTADOS)
    fallos = [n for ok, n, _ in RESULTADOS if not ok]
    print(f"\n{total - len(fallos)}/{total} chequeos pasaron.")
    if fallos:
        print("FAIL:")
        for n in fallos:
            print(f"  - {n}")
        return 1
    print("PASS: todo el loop anda (publicar, entrar con PIN, decidir, recibir y marcar).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
