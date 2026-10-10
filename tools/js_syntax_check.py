"""
Revisa la sintaxis estructural de los JS del frontend sin necesitar Node.

Comprueba delimitadores balanceados ( ), [ ] { }, cadenas, plantillas
`...` con ${ ... } anidados, comentarios y literales regex, e informa el
primer desbalance con línea y columna.

    python tools/js_syntax_check.py                      # revisa static/js/*.js
    python tools/js_syntax_check.py ruta/al/app.js
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KEYWORDS_RE = {"return", "typeof", "case", "in", "of", "do", "else", "void",
               "delete", "new", "instanceof", "yield", "await", "throw"}


def check(path):
    """Devuelve (ok, lineas_de_informe) para un archivo JS."""
    src = io.open(path, encoding="utf-8").read()
    stack = []
    errs = []
    i, line, col = 0, 1, 1
    prev_sig, prev_word = "", ""
    templates = 0

    def advance(n=1):
        nonlocal i, line, col
        for _ in range(n):
            if i < len(src) and src[i] == "\n":
                line += 1
                col = 1
            else:
                col += 1
            i += 1

    def fail(msg):
        errs.append("linea %d col %d: %s" % (line, col, msg))

    while i < len(src):
        ch = src[i]
        mode = stack[-1] if stack else "code"

        if mode != "tmpl" and ch == "/" and i + 1 < len(src) and src[i + 1] == "/":
            while i < len(src) and src[i] != "\n":
                advance()
            continue
        if mode != "tmpl" and ch == "/" and i + 1 < len(src) and src[i + 1] == "*":
            advance(2)
            while i < len(src) and not (src[i] == "*" and i + 1 < len(src) and src[i + 1] == "/"):
                advance()
            advance(2)
            continue

        if mode == "tmpl":
            if ch == "\\":
                advance(2)
                continue
            if ch == "`":
                stack.pop()
                templates += 1
                advance()
                prev_sig = "`"
                continue
            if ch == "$" and i + 1 < len(src) and src[i + 1] == "{":
                stack.append("expr")
                advance(2)
                prev_sig = "{"
                continue
            advance()
            continue

        if ch in ("'", '"'):
            quote = ch
            advance()
            while i < len(src):
                if src[i] == "\\":
                    advance(2)
                    continue
                if src[i] == quote:
                    advance()
                    break
                if src[i] == "\n":
                    fail("salto de linea dentro de cadena sin cerrar")
                    break
                advance()
            prev_sig = quote
            continue
        # literal regex (heuristica): tras ( , = : [ { ! & | ? ; + - * % ^ ~ < > o palabra clave
        if ch == "/" and (prev_word in KEYWORDS_RE or
                          prev_sig in ("(", ",", "=", ":", "[", "{", "!", "&", "|",
                                       "?", ";", "+", "-", "*", "%", "^", "~", "<", ">",
                                       "`", "")):
            in_class = False
            advance()
            while i < len(src):
                c = src[i]
                if c == "\\":
                    advance(2)
                    continue
                if c == "[":
                    in_class = True
                elif c == "]":
                    in_class = False
                elif c == "/" and not in_class:
                    advance()
                    break
                elif c == "\n":
                    break
                advance()
            prev_sig = "/"
            continue

        if ch == "`":
            stack.append("tmpl")
            advance()
            prev_sig = "`"
            continue

        if ch in "({[":
            stack.append({"(": "paren", "{": "brace", "[": "bracket"}[ch])
            advance()
            prev_sig, prev_word = ch, ""
            continue

        if ch in ")}]":
            if not stack:
                fail("cierre '%s' sin apertura" % ch)
                advance()
                continue
            top = stack[-1]
            if ch == "}" and top == "expr":
                stack.pop()          # cierra el ${ ... } y vuelve a la plantilla
                advance()
                prev_sig = "}"
                continue
            if ((ch == ")" and top == "paren") or (ch == "}" and top == "brace") or
                    (ch == "]" and top == "bracket")):
                stack.pop()
                advance()
                prev_sig = ch
                continue
            fail("cierre '%s' no coincide con '%s'" % (ch, top))
            advance()
            continue

        if not ch.isspace():
            prev_sig = ch
            if ch.isalnum() or ch in "_$":
                j = i
                while j < len(src) and (src[j].isalnum() or src[j] in "_$"):
                    j += 1
                prev_word = src[i:j]
            else:
                prev_word = ""
        advance()

    if stack:
        errs.append("cierres pendientes al final del archivo: " + ", ".join(map(str, stack)))

    out = ["%s (%d bytes, %d lineas, %d plantilla(s))" % (path, len(src), line, templates)]
    if errs:
        out.append("ERRORES (%d):" % len(errs))
        out.extend("  - " + e for e in errs[:25])
    else:
        out.append("  SINTAXIS ESTRUCTURAL OK")
    return (not errs), out


def main():
    args = sys.argv[1:]
    if args:
        targets = args
    else:
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "static", "js")
        targets = [os.path.join(base, f) for f in sorted(os.listdir(base))
                   if f.endswith(".js")]
    ok_all = True
    for path in targets:
        ok, lines = check(path)
        ok_all = ok_all and ok
        print("\n".join(lines))
    print("\nRESULTADO:", "TODO OK" if ok_all else "HAY ERRORES")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())