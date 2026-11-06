#!/usr/bin/env bash
# Instalador de Botonera: copia el skill, escribe la config local y deja listo el SQL para Supabase.
# macOS y Linux. Se puede correr más de una vez: reusa el BM_SECRET que ya exista.
#
# Uso:
#   ./install.sh --url https://xxxx.supabase.co --key <publishable/anon key>
#   ./install.sh --hook          # solo imprime el bloque para ~/.claude/settings.json
#
# Opciones:
#   --url <SUPABASE_URL>      URL del proyecto de Supabase (si falta, la pide)
#   --key <key>               key publishable/anon del proyecto (si falta, la pide)
#   --skill-dir <dir>         dónde instalar el skill (default ~/.claude/skills/botonera)
#   --zona <zona IANA>        zona horaria del aviso push (default: la del sistema, o UTC)
#   --avisar-url <url>        función de push (default <SUPABASE_URL>/functions/v1/bm-avisar)
#   --contacto <url|mailto:>  contacto de la firma VAPID de los avisos (default <SUPABASE_URL>)
#   --yes                     sin preguntas: pisa el directorio del skill si ya existe
#   --hook                    imprime el hook de entregar.py y sale (no toca settings.json)
#   -h, --help                esta ayuda
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
shopt -s nullglob
MIGRACIONES=("$AQUI"/supabase/migrations/*.sql)   # en orden de fecha: la base entera y sus agregados
shopt -u nullglob

URL=""
KEY=""
SKILL_DIR="$HOME/.claude/skills/botonera"
ZONA=""
AVISAR_URL=""
CONTACTO=""
SI=0
SOLO_HOOK=0

die() { echo "error: $*" >&2; exit 1; }
info() { echo "· $*"; }

ayuda() { sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --url)        [ $# -ge 2 ] || die "--url necesita un valor"; URL="$2"; shift 2 ;;
    --key)        [ $# -ge 2 ] || die "--key necesita un valor"; KEY="$2"; shift 2 ;;
    --skill-dir)  [ $# -ge 2 ] || die "--skill-dir necesita un valor"; SKILL_DIR="$2"; shift 2 ;;
    --zona)       [ $# -ge 2 ] || die "--zona necesita un valor"; ZONA="$2"; shift 2 ;;
    --avisar-url) [ $# -ge 2 ] || die "--avisar-url necesita un valor"; AVISAR_URL="$2"; shift 2 ;;
    --contacto)   [ $# -ge 2 ] || die "--contacto necesita un valor"; CONTACTO="$2"; shift 2 ;;
    --yes|-y)     SI=1; shift ;;
    --hook)       SOLO_HOOK=1; shift ;;
    -h|--help)    ayuda; exit 0 ;;
    *)            die "opción desconocida: $1 (probá --help)" ;;
  esac
done

# ~ al principio de --skill-dir (si llegó sin expandir)
case "$SKILL_DIR" in
  "~")   SKILL_DIR="$HOME" ;;
  "~/"*) SKILL_DIR="$HOME/${SKILL_DIR#\~/}" ;;
esac
SKILL_DIR="${SKILL_DIR%/}"
[ -n "$SKILL_DIR" ] || die "--skill-dir no puede ser la raíz"

# --- --hook: solo el bloque, sin tocar nada ---------------------------------------------------
if [ "$SOLO_HOOK" -eq 1 ]; then
  cat <<HOOK
Sumá esto a ~/.claude/settings.json (si ya tenés "hooks", mezclalo con lo que hay; este instalador no edita ese archivo):

{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command", "command": "python3 $SKILL_DIR/entregar.py" } ] }
    ],
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "python3 $SKILL_DIR/entregar.py" } ] }
    ]
  }
}

El hook es opcional: si el proceso que espera la respuesta (esperar.py) muere, vuelve a entregarla a la sesión.
HOOK
  exit 0
fi

# --- python3 >= 3.9 ---------------------------------------------------------------------------
command -v python3 >/dev/null 2>&1 || die "no encuentro python3 (hace falta la versión 3.9 o más nueva)"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
  || die "hace falta python3 3.9 o más nuevo (tenés $(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])'))"

[ -f "$AQUI/skill/armar.py" ] || die "no encuentro $AQUI/skill/armar.py: corré el instalador desde el repo clonado"
[ "${#MIGRACIONES[@]}" -gt 0 ] || die "faltan las migraciones en $AQUI/supabase/migrations (el repo está incompleto)"

# --- datos de Supabase ------------------------------------------------------------------------
preguntar() {  # preguntar <variable> <texto>
  local var="$1" texto="$2" valor=""
  if [ "$SI" -eq 1 ] || [ ! -t 0 ]; then
    die "falta $texto (pasalo con --url / --key)"
  fi
  read -r -p "$texto: " valor
  eval "$var=\$valor"
}

[ -n "$URL" ] || preguntar URL "URL de Supabase (https://<ref>.supabase.co)"
[ -n "$KEY" ] || preguntar KEY "Key publishable/anon de Supabase"
URL="${URL%/}"
case "$URL" in http://*|https://*) ;; *) die "la URL tiene que empezar con http:// o https:// (recibí: $URL)" ;; esac
case "$URL$KEY" in *[[:space:]]*|*\"*|*\'*|*\\*) die "la URL y la key no pueden tener espacios, comillas ni barras" ;; esac
[ -n "$KEY" ] || die "la key está vacía"

# --- zona horaria -----------------------------------------------------------------------------
zona_valida() { printf '%s' "$1" | grep -Eq '^[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+)*$'; }

detectar_zona() {
  local z=""
  if [ -n "${TZ:-}" ]; then z="${TZ#:}"; fi
  if ! zona_valida "$z" 2>/dev/null; then
    z=""
    if [ -L /etc/localtime ]; then
      z="$(readlink /etc/localtime 2>/dev/null | sed -n 's#.*/zoneinfo/##p')"
    fi
  fi
  if ! zona_valida "$z" 2>/dev/null && [ -r /etc/timezone ]; then
    z="$(head -n1 /etc/timezone 2>/dev/null | tr -d '[:space:]')"
  fi
  if ! zona_valida "$z" 2>/dev/null && command -v timedatectl >/dev/null 2>&1; then
    z="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
  fi
  if zona_valida "$z" 2>/dev/null; then echo "$z"; else echo "UTC"; fi
}

[ -n "$ZONA" ] || ZONA="$(detectar_zona)"
zona_valida "$ZONA" || die "la zona '$ZONA' no parece una zona IANA (ej. Europe/Madrid)"
[ -n "$AVISAR_URL" ] || AVISAR_URL="$URL/functions/v1/bm-avisar"
case "$AVISAR_URL" in *[[:space:]]*|*\'*) die "--avisar-url no puede tener espacios ni comillas simples" ;; esac

# --- skill ------------------------------------------------------------------------------------
copiar_skill=1
if [ -e "$SKILL_DIR" ]; then
  if [ "$SI" -eq 1 ]; then
    info "ya existe $SKILL_DIR: lo piso (--yes)"
  elif [ -t 0 ]; then
    read -r -p "Ya existe $SKILL_DIR. ¿Lo piso? [s/N]: " r
    case "$r" in s|S|si|SI|sí|Sí|y|Y|yes) ;; *) copiar_skill=0 ;; esac
  else
    die "ya existe $SKILL_DIR y no hay terminal para preguntar (usá --yes para pisarlo)"
  fi
fi
if [ "$copiar_skill" -eq 1 ]; then
  mkdir -p "$SKILL_DIR"
  cp -R "$AQUI/skill/." "$SKILL_DIR/"
  find "$SKILL_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
  info "skill instalado en $SKILL_DIR"
else
  info "dejo el skill como está en $SKILL_DIR"
fi

# --- config local (~/.config/botonera/env) ----------------------------------------------------
CONF_DIR="$HOME/.config/botonera"
ENV_FILE="$CONF_DIR/env"
mkdir -p "$CONF_DIR"
chmod 700 "$CONF_DIR"

SECRETO=""
if [ -f "$ENV_FILE" ]; then
  SECRETO="$(sed -n 's/^BM_SECRET=//p' "$ENV_FILE" | head -n1 | tr -d "\"' \t\r")"
fi
if [ -n "$SECRETO" ]; then
  info "reuso el BM_SECRET que ya había en $ENV_FILE"
else
  SECRETO="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
  info "generé un BM_SECRET nuevo"
fi

( umask 077
  {
    echo "SUPABASE_URL=$URL"
    echo "SUPABASE_ANON_KEY=$KEY"
    echo "BM_SECRET=$SECRETO"
  } > "$ENV_FILE" )
chmod 600 "$ENV_FILE"
info "config escrita en $ENV_FILE (permisos 600)"

# --- web/config.js (la key es pública/publishable: puede viajar al navegador) -----------------
if [ -d "$AQUI/web" ]; then
  python3 - "$URL" "$KEY" > "$AQUI/web/config.js" <<'PY'
import json, sys
print("window.BOTONERA_CONFIG = { supabaseUrl: %s, supabaseKey: %s };" % (json.dumps(sys.argv[1]), json.dumps(sys.argv[2])))
PY
  info "web/config.js escrito"
else
  echo "aviso: no existe $AQUI/web, no escribí config.js" >&2
fi

# --- SQL: instalar.sql (migración + bm_instalar) y bootstrap.sql (solo bm_instalar) -----------
LINEA="$(BM_SECRET="$SECRETO" python3 - "$AVISAR_URL" "$ZONA" "${CONTACTO:-$URL}" <<'PY'
import hashlib, os, sys
huella = hashlib.sha256(os.environ["BM_SECRET"].encode("utf-8")).hexdigest()
q = lambda x: "'" + x.replace("'", "''") + "'"
avisar, zona, contacto = sys.argv[1:4]
print("select public.bm_instalar(%s, %s, %s, %s);" % (q(huella), q(avisar), q(zona), q(contacto)))
PY
)"
[ -n "$LINEA" ] || die "no pude armar la llamada a bm_instalar"

( umask 077
  { for m in "${MIGRACIONES[@]}"; do cat "$m"; printf '\n'; done; printf '%s\n' "$LINEA"; } > "$CONF_DIR/instalar.sql"
  printf '%s\n' "$LINEA" > "$CONF_DIR/bootstrap.sql" )
chmod 600 "$CONF_DIR/instalar.sql" "$CONF_DIR/bootstrap.sql"
info "SQL escrito en $CONF_DIR/instalar.sql y $CONF_DIR/bootstrap.sql (permisos 600)"

# --- próximos pasos ---------------------------------------------------------------------------
REF=""
case "$URL" in
  https://*.supabase.co) REF="${URL#https://}"; REF="${REF%%.*}" ;;
esac
[ -n "$REF" ] || REF="<project-ref>"

cat <<PASOS

Listo. Faltan estos pasos, en este orden:

  1. Pegá el contenido de $CONF_DIR/instalar.sql en el SQL editor de Supabase y ejecutalo.
     (Si las migraciones ya están aplicadas, por ejemplo con "supabase start", pegá solo
     $CONF_DIR/bootstrap.sql. Si venís de una versión anterior, volvé a correr este
     instalador y pegá el instalar.sql nuevo: las migraciones se pueden repetir.)

  2. Desplegá la función de avisos push, desde la raíz del repo:
       supabase functions deploy bm-avisar --project-ref $REF --no-verify-jwt

  3. Desplegá la web:
       cd web && vercel deploy --prod

  4. Poné el PIN de 4 dígitos:
       python3 $SKILL_DIR/pin.py poner

  5. Abrí la web en el celular, instalala como app y prendé los avisos.

  6. En Claude Code, decí /botonera.

Opcional: para que las respuestas lleguen aunque se cierre la sesión, corré
  ./install.sh --hook
y sumá lo que imprime a ~/.claude/settings.json.

Opcional: para que un bot publique sin tu secret completo, corré
  python3 $SKILL_DIR/secret-bot.py
y ejecutá el SQL que imprime.
PASOS
