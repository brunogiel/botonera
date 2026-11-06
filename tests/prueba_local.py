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
  5. Editar (campos que vuelven en la respuesta), retomar una tanda decidida con `retomar.py`, la fila
     «Con error» (`errores.py`, listar y marcar «Visto») y el secret de bot, que solo sirve para claves `bot-`.

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

    def py(script, *a, timeout=60, entorno=None):
        return correr([sys.executable, str(skill / script), *a], env=entorno or env, timeout=timeout)

    def sql(texto):
        return correr(["docker", "exec", "-i", contenedor, "psql", "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-t", "-A"],
                      entrada=texto, timeout=60)

    def leer_env(ruta):
        cfg = {}
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.strip().startswith("#"):
                k, v = linea.split("=", 1)
                cfg[k.strip()] = v.strip()
        return cfg

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
            "bm_rol": {"p_secret": "x"},
            "bm_es_bot": {"p_texto": "bot-x"},
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


        # 6b. Editar (campos), retomar, «Con error» y rol de bot. El token del paso 3 sigue vivo (el PIN cambia al final).
        print("\nEditar: campos que viajan y vuelven")
        secreto = leer_env(env_file)["BM_SECRET"]

        def armar_variante(nombre, cambio, extra=()):
            d = copy.deepcopy(datos)
            d["clave"] = f"{clave}-{nombre}"
            cambio(d)
            ruta = tmp / f"{nombre}.json"
            ruta.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            return py("armar.py", *extra, str(ruta), str(tmp / f"{nombre}.html"))

        seis = [{"id": f"c{i}", "etiqueta": f"Campo {i}", "valor": "x", "tipo": "texto"} for i in range(6)]
        r = armar_variante("seis", lambda d: d["items"][0].__setitem__("campos", seis), ("--html",))
        registrar(r.returncode == 1 and "'campos' tiene que ser una lista de 1 a 5" in r.stderr,
                  "armar.py rechaza más de 5 campos", r.stderr)
        r = armar_variante("tipo", lambda d: d["items"][0]["campos"][0].__setitem__("tipo", "color"), ("--html",))
        registrar(r.returncode == 1 and "tiene que ser texto | numero | fecha | opcion" in r.stderr,
                  "armar.py rechaza un tipo de campo desconocido", r.stderr)
        r = armar_variante("etiqueta", lambda d: d["items"][0]["campos"][0].__setitem__("etiqueta", "una etiqueta con muchas más de seis palabras"), ("--html",))
        registrar(r.returncode == 1 and "palabras (techo 6)" in r.stderr, "armar.py rechaza una etiqueta de más de 6 palabras", r.stderr)
        r = armar_variante("en-opciones", lambda d: d["items"][1].__setitem__("campos", d["items"][0]["campos"]), ("--html",))
        registrar(r.returncode == 1 and "'campos' va solo en cards sí/no" in r.stderr, "armar.py rechaza campos en una card con opciones", r.stderr)
        r = armar_variante("aplicar", lambda d: d["items"][0].__setitem__("aplicar", {"quizas": "algo"}), ("--html",))
        registrar(r.returncode == 1 and "no es una respuesta de esta card" in r.stderr, "armar.py rechaza una clave de aplicar que no es una respuesta", r.stderr)
        r = armar_variante("aplicar-largo", lambda d: d["items"][0].__setitem__("aplicar", {"va": " ".join(["palabra"] * 41)}), ("--html",))
        registrar(r.returncode == 1 and "techo 40" in r.stderr, "armar.py rechaza un plan de aplicar de más de 40 palabras", r.stderr)
        r = armar_variante("sin-aplicar", lambda d: [i.pop("aplicar", None) for i in d["items"]], ("--html",))
        registrar(r.returncode == 0 and "sin 'aplicar'" in r.stderr, "armar.py avisa (sin frenar) cuando faltan los planes de aplicar", r.stderr)

        clave_c = f"{clave}-campos"
        ruta_c = tmp / "campos.json"
        d_c = copy.deepcopy(datos)
        d_c["clave"] = clave_c
        ruta_c.write_text(json.dumps(d_c, ensure_ascii=False), encoding="utf-8")
        r = py("armar.py", "--publicar", str(ruta_c), str(tmp / "campos.html"))
        registrar(r.returncode == 0 and f"maestro: creada · {clave_c}" in r.stdout and "aviso" not in r.stderr,
                  "armar.py --publicar sube una tanda con campos y planes de aplicar", r.stderr or r.stdout)
        st, fl = rpc("bm_fila", {"p_token": token, "p_clave": clave_c})
        f = fl[0] if isinstance(fl, list) and fl else {}
        campos = ((f.get("datos") or {}).get("items") or [{}])[0].get("campos") or []
        registrar([c.get("id") for c in campos] == ["precio", "desde", "alcance"] and campos[0].get("valor") == 3500,
                  "los campos viajan a la base tal cual", f"{st} {str(campos)[:200]}")

        respuesta_c = (f"/botonera respuesta · {clave_c}\n"
                       "1. va con cambios · Subir el precio de los envíos → Subir el envío · "
                       "campos: precio=4200 (antes 3500); desde=2026-11-22 (antes 2026-11-15) · comentario: Solo hasta fin de mes.\n"
                       "2. eligió whatsapp · Elegir el canal para los avisos → Mensaje de WhatsApp\n"
                       "3. sin marcar · Archivar los pedidos viejos")
        st, res = rpc("bm_decidir_pin", {"p_token": token, "p_clave": clave_c, "p_respuesta": respuesta_c})
        registrar(st == 200 and res == "decidida", "la respuesta «va con cambios · campos: …» se guarda entera", f"{st} {res}")

        print("\nRetomar sin la sesión viva")
        st, res = rpc("bm_retomar", {"p_secret": secreto, "p_clave": clave_c})
        its = res.get("items") if isinstance(res, dict) else []
        registrar(st == 200 and res.get("estado") == "decidida" and res.get("respuesta_texto") == respuesta_c and len(its) == 3
                  and "Cambiar la tarifa" in (its[0].get("aplicar") or {}).get("va", "") and "whatsapp" in (its[1].get("aplicar") or {}),
                  "bm_retomar trae la respuesta y el plan aplicar de cada ítem, sin cambiar el estado", f"{st} {str(res)[:200]}")
        st, res = rpc("bm_retomar", {"p_secret": secreto, "p_clave": "clave-que-no-existe"})
        registrar(st == 200 and isinstance(res, dict) and res.get("estado") == "no_existe", "bm_retomar sobre una clave inexistente dice no_existe", f"{st} {res}")
        st, res = rpc("bm_retomar", {"p_secret": "secreto-falso", "p_clave": clave_c})
        registrar(st >= 400 and "secret invalido" in mensaje(res), "bm_retomar con secreto equivocado se rechaza", f"{st} {res}")
        r = py("retomar.py", clave_c)
        registrar(r.returncode == 0 and "precio=4200 (antes 3500)" in r.stdout and "Cambiar la tarifa" in r.stdout
                  and "[whatsapp] Pedir el alta" in r.stdout and "sin marcar: no se hace" in r.stdout,
                  "retomar.py arma el brief: los valores nuevos, el plan de cada respuesta y lo sin marcar", r.stdout + r.stderr)
        r = py("retomar.py", clave_c, "--json")
        try:
            a = json.loads(r.stdout)
        except ValueError:
            a = {}
        registrar(r.returncode == 0 and a.get("todo_con_plan") is True and a["items"][0]["campos"].startswith("precio=4200")
                  and a["items"][0]["comentario"] == "Solo hasta fin de mes." and a["items"][2]["accion"] == "nada",
                  "retomar.py --json separa campos, comentario y acción de cada ítem", r.stdout[:200] + r.stderr)
        r = py("retomar.py", clave_c, "--tomar")
        st, fl = rpc("bm_fila", {"p_token": token, "p_clave": clave_c})
        f = fl[0] if isinstance(fl, list) and fl else {}
        registrar(r.returncode == 0 and f.get("estado") == "recibida", "retomar.py --tomar pasa la tanda de decidida a recibida", f"{r.stderr} {f.get('estado')}")
        r = py("retomar.py", "clave-que-no-existe")
        registrar(r.returncode == 1 and "no existe" in r.stderr, "retomar.py sobre una clave inexistente sale con 1", r.stdout + r.stderr)

        print("\nColgadas y fila «Con error»")
        r = py("colgadas.py")
        registrar(r.returncode == 0 and clave_c in r.stdout and "plan aplicar 3/3" in r.stdout,
                  "colgadas.py lista la tanda recibida con su «plan aplicar 3/3»", r.stdout + r.stderr)
        r = py("colgadas.py", "--archivar", clave_c, "la sesión ya no está")
        registrar(r.returncode == 0 and "→ archivada (antes: recibida)" in r.stdout and "errores: creado" in r.stdout,
                  "colgadas.py --archivar archiva y publica un error si había una respuesta sin aplicar", r.stdout + r.stderr)

        def errores_vistos():
            st_, lista_ = rpc("bm_errores_lista", {"p_token": token})
            return st_, (lista_ if isinstance(lista_, list) else [])
        st, lista = errores_vistos()
        e_sesion = next((e for e in lista if e.get("origen_id") == clave_c), None)
        registrar(st == 200 and e_sesion is not None and e_sesion.get("tipo") == "sesion" and clave_c in e_sesion.get("titulo", ""),
                  "bm_errores_lista (con token) muestra el error de la tanda archivada sin aplicar", f"{st} {str(lista)[:200]}")

        tarea_id = f"tarea-prueba-{int(time.time())}"
        err_tarea = {"tipo": "tarea", "origen_id": tarea_id, "titulo": "Tarea de prueba", "motivo": "Límite de uso",
                     "ocurrio_at": "2026-11-01T03:00:00Z"}
        r = py("errores.py", "publicar", json.dumps(err_tarea), "--seco")
        registrar(r.returncode == 0 and "WOULD publish" in r.stdout, "errores.py --seco muestra lo que publicaría", r.stdout + r.stderr)
        st, lista = errores_vistos()
        registrar(not any(e.get("origen_id") == tarea_id for e in lista), "…y no escribe nada", str(lista)[:200])
        r = py("errores.py", "publicar", json.dumps(err_tarea))
        registrar(r.returncode == 0 and "errores: 1 creado" in r.stdout, "errores.py publicar crea el error", r.stdout + r.stderr)
        r = py("errores.py", "publicar", json.dumps(err_tarea))
        registrar(r.returncode == 0 and "errores: 1 repetido" in r.stdout, "publicar dos veces el mismo error no lo duplica", r.stdout + r.stderr)
        ahora = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        runs = {"taskId": f"tarea-runs-{int(time.time())}", "runs": [
            {"status": "failed", "started_at": ahora, "error": "401 invalid_grant", "title": "Tarea con runs"},
            {"status": "failed", "started_at": "2020-01-01T00:00:00Z", "error": "viejo"},
            {"status": "success", "started_at": ahora}]}
        ruta_runs = tmp / "runs.json"
        ruta_runs.write_text(json.dumps(runs), encoding="utf-8")
        r = py("errores.py", "desde-runs", str(ruta_runs))
        registrar(r.returncode == 0 and "errores: 1 creado" in r.stdout and "401 invalid_grant" in r.stdout,
                  "errores.py desde-runs publica solo los runs fallidos de las últimas 24 h", r.stdout + r.stderr)
        st, res = rpc("bm_error_publicar", {"p_secret": "secreto-falso", "p_tipo": "tarea", "p_origen_id": "x", "p_titulo": "x",
                                            "p_motivo": None, "p_ocurrio_at": ahora})
        registrar(st >= 400 and "secret invalido" in mensaje(res), "bm_error_publicar con secreto equivocado se rechaza", f"{st} {res}")
        st, res = rpc("bm_error_publicar", {"p_secret": secreto, "p_tipo": "otro", "p_origen_id": "x", "p_titulo": "x",
                                            "p_motivo": None, "p_ocurrio_at": ahora})
        registrar(st >= 400 and "tipo invalido" in mensaje(res), "bm_error_publicar rechaza un tipo desconocido", f"{st} {res}")
        st, res = rpc("bm_errores_lista", {"p_token": "token-falso"})
        registrar(st >= 400 and "token invalido" in mensaje(res), "bm_errores_lista con token falso se rechaza", f"{st} {res}")
        st, res = http("GET", f"{url}/rest/v1/bm_errores?select=titulo", key)
        registrar((st in (401, 403)) or (st == 200 and res == []), "la clave pública sola no puede leer la tabla bm_errores", f"{st} {str(res)[:120]}")
        st, lista = errores_vistos()
        e_tarea = next((e for e in lista if e.get("origen_id") == tarea_id), None)
        registrar(e_tarea is not None and len(lista) >= 3, "la lista trae los errores sin ver", str(lista)[:300])
        ids = [e["id"] for e in lista]
        st, res = rpc("bm_error_visto", {"p_token": token, "p_id": e_tarea["id"]})
        registrar(st == 200 and res is True, "bm_error_visto marca uno como visto", f"{st} {res}")
        st, res = rpc("bm_error_visto", {"p_token": token, "p_id": e_tarea["id"]})
        registrar(st == 200 and res is False, "marcar visto dos veces devuelve false", f"{st} {res}")
        st, lista2 = errores_vistos()
        registrar([e["id"] for e in lista2] == [i for i in ids if i != e_tarea["id"]], "el error visto sale de la lista y los demás quedan",
                  f"{[e['id'] for e in lista2]} vs {ids}")
        st, res = rpc("bm_error_visto", {"p_token": "token-falso", "p_id": 1})
        registrar(st >= 400 and "token invalido" in mensaje(res), "bm_error_visto con token falso se rechaza", f"{st} {res}")
        for e in lista2:   # la prueba deja la fila «Con error» vacía
            rpc("bm_error_visto", {"p_token": token, "p_id": e["id"]})

        print("\nRol de bot")
        r = py("secret-bot.py")
        env_bot = home / ".config" / "botonera" / "env-bot"
        m = re.search(r"'([0-9a-f]{64})'", r.stdout)
        cfg_bot = leer_env(env_bot) if env_bot.exists() else {}
        bs = cfg_bot.get("BM_SECRET", "")
        registrar(r.returncode == 0 and m and bs and bs not in r.stdout and oct(env_bot.stat().st_mode & 0o777) == "0o600",
                  "secret-bot.py escribe env-bot (600), imprime el hash y nunca el secret", r.stderr or r.stdout[-200:])
        r = py("secret-bot.py")
        registrar(r.returncode != 0 and "ya existe" in (r.stderr + r.stdout), "secret-bot.py no pisa un env-bot existente sin --rotar", r.stdout + r.stderr)
        st, res = rpc("bm_pendientes", {"p_secret": bs, "p_horas": 0})
        registrar(st >= 400 and "secret invalido" in mensaje(res), "mientras el hash no está cargado el secret de bot no entra a nada", f"{st} {res}")
        r = sql(f"insert into public.bm_config (k, v) values ('bot_secret_sha256', '{m.group(1)}') on conflict (k) do update set v = excluded.v;")
        registrar(r.returncode == 0, "se carga el hash del secret de bot", r.stderr)

        cb = f"bot-prueba-{int(time.time())}"
        datos_bot = {"titulo": "Tanda de un bot", "clave": cb, "items": [{"n": 1, "titulo": "Algo del bot"}]}
        def publicar_bot(c, session, skill="otro"):
            return rpc("bm_publicar", {"p_secret": bs, "p_clave": c, "p_session_id": session, "p_sesion_titulo": "Bot",
                                       "p_skill": skill, "p_proyecto": None, "p_titulo": "Tanda de un bot", "p_n_items": 1,
                                       "p_datos": datos_bot, "p_html": "<html></html>"})
        st, res = publicar_bot(cb, "bot-agente")
        registrar(st == 200 and res == "creada", "el secret de bot publica una clave bot- con session_id bot-", f"{st} {res}")
        st, lista = rpc("bm_lista", {"p_token": token})
        fb = next((x for x in lista if x.get("clave") == cb), {}) if isinstance(lista, list) else {}
        registrar(fb.get("skill") == "bot" and fb.get("session_id") == "bot-agente", "el servidor fuerza skill = bot", str(fb)[:200])
        st, res = publicar_bot("tanda-comun", "bot-agente")
        registrar(st >= 400 and "rol bot: solo claves bot-" in mensaje(res), "el secret de bot no publica una clave que no empieza con bot-", f"{st} {res}")
        st, res = publicar_bot(cb, "sesion-de-claude-code")
        registrar(st >= 400 and "session_id tiene que empezar con bot-" in mensaje(res), "el secret de bot no ata su tanda a una sesión de Claude Code", f"{st} {res}")
        st, res = publicar_bot(cb, None)
        registrar(st >= 400 and "session_id tiene que empezar con bot-" in mensaje(res), "…ni publica sin session_id", f"{st} {res}")
        for nombre, cuerpo in (("bm_recibir", {"p_clave": clave}), ("bm_marcar", {"p_clave": clave, "p_estado": "archivada", "p_resumen": "x"}),
                               ("bm_retomar", {"p_clave": clave})):
            st, res = rpc(nombre, dict(cuerpo, p_secret=bs))
            registrar(st >= 400 and "rol bot: solo claves bot-" in mensaje(res), f"{nombre} con el secret de bot no toca una clave ajena", f"{st} {res}")
        for nombre, cuerpo in (("bm_poner_pin", {"p_pin": "1111"}), ("bm_desbloquear", {}), ("bm_estado_pin", {}), ("bm_sin_cerrar", {}),
                               ("bm_estado_avisos", {})):
            st, res = rpc(nombre, dict(cuerpo, p_secret=bs))
            registrar(st >= 400 and "secret invalido" in mensaje(res), f"{nombre} no acepta el secret de bot", f"{st} {res}")
        st, res = rpc("bm_error_publicar", {"p_secret": bs, "p_tipo": "tarea", "p_origen_id": "x", "p_titulo": "x", "p_motivo": None, "p_ocurrio_at": ahora})
        registrar(st >= 400 and "rol bot: no publica errores" in mensaje(res), "el secret de bot no publica errores", f"{st} {res}")
        r = py("colgadas.py")
        registrar(r.returncode == 0 and cb not in r.stdout and "bot- salteadas" in r.stdout, "colgadas.py no lista las tandas bot-", r.stdout + r.stderr)
        r = py("colgadas.py", "--archivar", cb, "prueba")
        registrar(r.returncode == 1 and "es de un bot" in r.stdout, "colgadas.py --archivar no archiva una tanda bot-", r.stdout + r.stderr)

        # pendientes: el bot ve solo lo suyo; el secret total ve todo
        clave_o = f"{clave}-otra"
        d_o = copy.deepcopy(datos)
        d_o["clave"] = clave_o
        (tmp / "otra.json").write_text(json.dumps(d_o, ensure_ascii=False), encoding="utf-8")
        py("armar.py", "--publicar", str(tmp / "otra.json"), str(tmp / "otra.html"))
        for c in (clave_o, cb):
            rpc("bm_decidir_pin", {"p_token": token, "p_clave": c, "p_respuesta": f"/botonera respuesta · {c}\n1. va · x"})
        st, pb = rpc("bm_pendientes", {"p_secret": bs, "p_horas": 0})
        st2, pt = rpc("bm_pendientes", {"p_secret": secreto, "p_horas": 0})
        claves_b = sorted(x["clave"] for x in pb) if isinstance(pb, list) else None
        claves_t = {x["clave"] for x in pt} if isinstance(pt, list) else set()
        registrar(claves_b == [cb] and {cb, clave_o} <= claves_t,
                  "bm_pendientes: el bot ve solo sus tandas bot-, el secret total ve todas", f"bot={claves_b} total={sorted(claves_t)}")
        st, res = rpc("bm_recibir", {"p_secret": bs, "p_clave": cb})
        registrar(st == 200 and res.get("estado") == "recibida" and res.get("respuesta_texto", "").endswith("1. va · x"),
                  "bm_recibir con el secret de bot entrega la respuesta de su tanda", f"{st} {res}")
        st, res = rpc("bm_marcar", {"p_secret": bs, "p_clave": cb, "p_estado": "aplicada", "p_resumen": "hecho"})
        registrar(st == 200 and res.get("cambiado") is True, "bm_marcar con el secret de bot cierra su tanda", f"{st} {res}")
        py("marcar.py", clave_o, "archivada", "fin de la prueba")

        # el bot por variables de entorno (sin archivo de config): armar.py, esperar.py y session_id bot-
        home_bot = tmp / "home-bot"
        home_bot.mkdir()
        entorno_bot = dict(env, HOME=str(home_bot), SUPABASE_URL=url, SUPABASE_ANON_KEY=key, BM_SECRET=bs, BM_SESSION_ID="bot-por-env")
        cb2 = f"bot-env-{int(time.time())}"
        d_b = copy.deepcopy(datos)
        d_b["clave"] = cb2
        (tmp / "bot.json").write_text(json.dumps(d_b, ensure_ascii=False), encoding="utf-8")
        r = py("armar.py", "--publicar", str(tmp / "bot.json"), str(tmp / "bot.html"), entorno=entorno_bot)
        st, fl = rpc("bm_fila", {"p_token": token, "p_clave": cb2})
        f = fl[0] if isinstance(fl, list) and fl else {}
        registrar(r.returncode == 0 and f"creada · {cb2}" in r.stdout and not (home_bot / ".config").exists(),
                  "armar.py publica como bot con SUPABASE_URL, SUPABASE_ANON_KEY y BM_SECRET en el entorno", r.stderr or r.stdout)
        sesion_bot = f.get("session_id") if f else None
        registrar(not (home_bot / ".cache" / "botonera" / "sesiones" / "bot-por-env").exists(),
                  "una sesión bot- no deja la marca que despierta al hook entregar.py", str(sesion_bot))
        r = py("armar.py", "--publicar", str(ruta_c), str(tmp / "campos2.html"), entorno=entorno_bot)
        registrar("rol bot: solo claves bot-" in r.stderr, "armar.py como bot no publica una clave que no es suya (avisa y sigue)", r.stderr + r.stdout)
        proc = subprocess.Popen([sys.executable, str(skill / "esperar.py"), cb2, "--cada", "1"], env=entorno_bot,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(2)
        respuesta_b = f"/botonera respuesta · {cb2}\n1. va · Subir el precio de los envíos → Subir el envío"
        rpc("bm_decidir_pin", {"p_token": token, "p_clave": cb2, "p_respuesta": respuesta_b})
        try:
            out_b, err_b = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            out_b, err_b = proc.communicate()
        registrar(proc.returncode == 0 and out_b.strip() == respuesta_b, "esperar.py como bot recibe la respuesta de su tanda", f"rc={proc.returncode} {out_b[:150]!r} {err_b[:150]!r}")
        py("marcar.py", cb2, "aplicada", "hecho", entorno=entorno_bot)

        r = sql("delete from public.bm_config where k = 'bot_secret_sha256';")
        st, res = rpc("bm_pendientes", {"p_secret": bs, "p_horas": 0})
        registrar(r.returncode == 0 and st >= 400 and "secret invalido" in mensaje(res), "borrar la fila da de baja al bot", f"{st} {res}")

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
