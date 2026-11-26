#!/usr/bin/env python3
"""Chequea que ninguna clase con CSS en la versión de referencia (por defecto origin/main) se haya quedado sin CSS
en web/index.html mientras el HTML/JS nuevo todavía la usa. Atrapa estilos perdidos al fusionar.

Uso:  python3 tests/check-css.py [--base <archivo.html>]
Sin --base lee `git show origin/main:web/index.html`; si no hay referencia (clon sin esa rama), avisa y sale 0.
Sale con 1 y lista las clases si falta alguna."""
import re, subprocess, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
NUEVA = RAIZ / "web" / "index.html"


def partes(html):
    css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))
    resto = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.S)
    return css, resto


def clases_css(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    selectores = " ".join(re.findall(r"([^{}]+)\{", css))
    return set(re.findall(r"\.([A-Za-z_][\w-]*)", selectores))


def clases_usadas(resto):
    usadas = set()
    for m in re.finditer(r"class(?:Name)?\s*=\s*[\"']([^\"']*)[\"']", resto):
        usadas.update(t for t in m.group(1).split() if re.fullmatch(r"[A-Za-z_][\w-]*", t))
    for m in re.finditer(r"classList\.(?:add|toggle|remove|contains)\(([^)]*)\)", resto):
        usadas.update(re.findall(r"[\"']([A-Za-z_][\w-]*)[\"']", m.group(1)))
    return usadas


def main():
    args = sys.argv[1:]
    if "--base" in args:
        base = Path(args[args.index("--base") + 1]).read_text(encoding="utf-8")
    else:
        r = subprocess.run(["git", "-C", str(RAIZ), "show", "origin/main:web/index.html"], capture_output=True, text=True)
        if r.returncode != 0:
            print("check-css: no hay referencia (origin/main:web/index.html); no hay nada que comparar")
            return 0
        base = r.stdout
    css_base, _ = partes(base)
    css_nuevo, resto_nuevo = partes(NUEVA.read_text(encoding="utf-8"))
    faltan = sorted((clases_css(css_base) & clases_usadas(resto_nuevo)) - clases_css(css_nuevo))
    if faltan:
        print(f"check-css: {len(faltan)} clases tenían CSS en la referencia, se usan y ya no lo tienen: {', '.join(faltan)}")
        return 1
    print("check-css: ok · toda clase con CSS en la referencia y en uso sigue con CSS")
    return 0


sys.exit(main())
