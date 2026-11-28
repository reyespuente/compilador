import json
import textwrap
from collections import Counter
from decimal import Decimal

PRECEDENCIA = {
    "||": 1,
    "&&": 2,
    "==": 3, "!=": 3, "<": 3, ">": 3, "<=": 3, ">=": 3,
    "+": 4, "-": 4,
    "*": 5, "/": 5,
}


def formatear_tabla(encabezados, filas, a_la_derecha=()):
    if not filas:
        return ""

    filas = [encabezados] + [[str(valor) for valor in fila] for fila in filas]
    anchos = [max(map(len, columna)) for columna in zip(*filas)]
    lineas = []
    for fila in filas:
        partes = []
        for indice, (texto, ancho) in enumerate(zip(fila, anchos)):
            if indice in a_la_derecha:
                partes.append(texto.rjust(ancho))
            else:
                partes.append(texto.ljust(ancho))
        lineas.append("  ".join(partes).rstrip())
    return "\n".join(lineas)


def tabla_tokens_texto(tokens):
    lineas = [f"{'LÍN':>4}:{'COL':<4} {'TIPO':<16} LEXEMA"]

    if not tokens:
        lineas.append("(SIN TOKENS)")
        return "\n".join(lineas)

    for token in tokens:
        lineas.append(
            f"{token.linea:>4}:{token.columna:<4} "
            f"{token.tipo:<16} {token.lexema}"
        )

    return "\n".join(lineas)


def linea_error(error, color="", reset=""):
    detalle = f" ({error.lexema!r})" if error.lexema else ""
    return (
        f"{color}ERROR {error.codigo}{reset} EN "
        f"{error.linea}:{error.columna}: {error.mensaje}{detalle}"
    )


def texto_errores(errores):
    return "\n".join(linea_error(error) for error in errores) or "(SIN ERRORES)"


def detalle_ast(nodo):
    if nodo.tipo == "principal":
        return "entero principal()"
    if nodo.tipo == "declaracion":
        datos = nodo.valor
        prefijo = "constante " if datos.get("constante") else ""
        detalle = f"{prefijo}{datos.get('tipo')} {datos.get('nombre')}"
    elif nodo.tipo in ("asignacion", "identificador"):
        detalle = str(nodo.valor)
    elif nodo.tipo in ("binaria", "comparacion", "logica", "cadena"):
        return str(nodo.valor)
    elif nodo.tipo == "negacion":
        return "!"
    elif nodo.tipo == "literal":
        tipo, valor = nodo.valor
        return f"{tipo} {valor_texto(valor)}"
    else:
        return ""

    if nodo.id_simbolo is not None:
        detalle += f" (ID {nodo.id_simbolo})"
    return detalle


def etiqueta_arbol(nodo):
    etiqueta = nodo.tipo.upper()
    detalle = detalle_ast(nodo)
    if detalle:
        etiqueta += f" ({detalle})"
    return etiqueta


def dibujar_arbol(nodo, prefijo="", conector="", extension=""):
    yield prefijo + conector + etiqueta_arbol(nodo)
    prefijo += extension
    hijos = [hijo for hijo in nodo.hijos if hijo is not None]
    for indice, hijo in enumerate(hijos):
        if indice == len(hijos) - 1:
            yield from dibujar_arbol(hijo, prefijo, "└── ", "    ")
        else:
            yield from dibujar_arbol(hijo, prefijo, "├── ", "│   ")


def arbol_dibujado_texto(arbol):
    if arbol is None:
        return ""
    return "\n".join(dibujar_arbol(arbol))


def _fuente_imagen(ImageFont, tamano):
    try:
        return ImageFont.truetype("DejaVuSansMono.ttf", tamano)
    except OSError:
        return ImageFont.load_default(size=tamano)


def _lineas_nodo_imagen(nodo):
    return [nodo.tipo.upper()] + textwrap.wrap(
        detalle_ast(nodo), width=13, max_lines=3, placeholder="..."
    )


def _distribuir_arbol(arbol, separacion):
    def medir(nodo):
        hijos = []
        limites = []
        for hijo in nodo.hijos:
            if hijo is None:
                continue
            plan, contorno = medir(hijo)
            x = max(
                (derecha + separacion - izquierda
                 for (_, derecha), (izquierda, _) in zip(limites, contorno)),
                default=0,
            )
            hijos.append((x, plan))
            for nivel, (izquierda, derecha) in enumerate(contorno):
                izquierda, derecha = izquierda + x, derecha + x
                if nivel == len(limites):
                    limites.append((izquierda, derecha))
                else:
                    limites[nivel] = (limites[nivel][0], derecha)

        centro = (hijos[0][0] + hijos[-1][0]) // 2 if hijos else 0
        plan = (nodo, [(x - centro, hijo) for x, hijo in hijos])
        contorno = [(0, 0)] + [(a - centro, b - centro) for a, b in limites]
        return plan, contorno

    nodos, ramas = [], []

    def colocar(plan, x, nivel):
        nodo, hijos = plan
        nodos.append((nodo, (x, nivel)))
        for desplazamiento, hijo in hijos:
            x_hijo = x + desplazamiento
            ramas.append(((x, nivel), (x_hijo, nivel + 1)))
            colocar(hijo, x_hijo, nivel + 1)

    plan, _ = medir(arbol)
    colocar(plan, 0, 0)
    return nodos, ramas


def generar_imagen_arbol(arbol, ruta, nombre):
    from PIL import Image, ImageDraw, ImageFont

    if arbol is None:
        raise ValueError("NO HAY ÁRBOL PARA DIBUJAR")

    fuente = _fuente_imagen(ImageFont, 12)
    fuente_titulo = _fuente_imagen(ImageFont, 20)
    radio = 54
    paso_x, paso_y = 124, 150
    margen, inicio_y = 24, 92
    fondo, tinta, relleno = "#111a14", "#88eea1", "#172b1d"
    nodos, ramas = _distribuir_arbol(arbol, paso_x)
    izquierda = min(x for _, (x, _) in nodos)
    derecha = max(x for _, (x, _) in nodos)
    ultimo_nivel = max(nivel for _, (_, nivel) in nodos)
    titulo = f"ÁRBOL SINTÁCTICO · {nombre}"
    ancho_arbol = derecha - izquierda + 2 * (margen + radio)
    ancho = max(ancho_arbol, int(fuente_titulo.getlength(titulo)) + 2 * margen + 1)
    alto = inicio_y + ultimo_nivel * paso_y + radio + margen
    imagen = Image.new("RGB", (ancho, alto), fondo)
    dibujo = ImageDraw.Draw(imagen)
    dibujo.text((margen, 12), titulo, font=fuente_titulo, fill=tinta)
    origen_x = (ancho - ancho_arbol) // 2 + margen + radio - izquierda

    def pixel(punto):
        x, nivel = punto
        return origen_x + x, inicio_y + nivel * paso_y

    for padre, hijo in ramas:
        dibujo.line([pixel(padre), pixel(hijo)], fill="#50795a", width=2)

    for nodo, centro in nodos:
        x, y = pixel(centro)
        dibujo.ellipse(
            (x - radio, y - radio, x + radio, y + radio),
            fill=relleno, outline=tinta, width=2,
        )
        lineas = _lineas_nodo_imagen(nodo)
        arriba = y - 7 * (len(lineas) - 1)
        for indice, linea in enumerate(lineas):
            dibujo.text(
                (x, arriba + 14 * indice), linea, anchor="mm", font=fuente,
                fill=tinta if indice == 0 else "#d5ebd8",
            )

    imagen.save(ruta, "PNG")


def valor_texto(valor):
    if valor is None:
        return "SIN ASIGNAR"
    if isinstance(valor, str):
        return repr(valor)
    if isinstance(valor, Decimal):
        return format(valor, "f")
    return str(valor)


def almacenamiento_texto(registro):
    desplazamiento = registro["almacenamiento"]
    if desplazamiento is None:
        return "NO ASIGNADA"
    return f"[rbp - {-desplazamiento}]"


def tabla_simbolos_texto(tabla):
    filas = []
    for registro in tabla.registros:
        inicializador = registro["inicializador"]
        filas.append([
            str(registro["id"]),
            registro["nombre"],
            registro["categoria"],
            registro["tipo"],
            formatear_expresion(inicializador) if inicializador is not None else "SIN INICIALIZADOR",
            "SÍ" if registro["modificable"] else "NO",
            f"{registro['linea']}:{registro['columna']}",
            str(len(registro["usos"])),
            almacenamiento_texto(registro),
        ])

    return formatear_tabla(
        ["ID", "NOMBRE", "CATEGORÍA", "TIPO", "INICIALIZADOR",
         "MOD", "LÍN:COL", "USOS", "UBICACIÓN"],
        filas, (0, 6, 7),
    )


def referencias_texto(tabla):
    filas = []
    for registro in tabla.registros:
        if not registro["usos"]:
            continue
        referencias = ", ".join(f"{linea}:{columna}" for linea, columna in registro["usos"])
        filas.append([registro["id"], registro["nombre"], referencias])
    return formatear_tabla(["ID", "NOMBRE", "REFERENCIAS"], filas, (0,))


def formatear_expresion(nodo, padre=0):
    if nodo is None or nodo.tipo == "error":
        return "?"

    if nodo.tipo == "literal":
        _, valor = nodo.valor
        return valor_texto(valor)

    if nodo.tipo == "identificador":
        return str(nodo.valor)

    if nodo.tipo == "negacion":
        texto = "!" + formatear_expresion(nodo.hijos[0], 6)
        return f"({texto})" if 6 < padre else texto

    if nodo.tipo in ("binaria", "comparacion", "logica"):
        operador = nodo.valor
        precedencia = PRECEDENCIA[operador]
        izquierda = formatear_expresion(nodo.hijos[0], precedencia)
        derecha = formatear_expresion(nodo.hijos[1], precedencia + 1)
        texto = f"{izquierda} {operador} {derecha}"
        return f"({texto})" if precedencia < padre else texto

    return "?"


def lineas_bloque(bloque, nivel, encabezado=""):
    sangria = "    " * nivel
    prefijo = encabezado + " " if encabezado else ""
    lineas = [f"{sangria}{prefijo}{{"]

    for instruccion in bloque.hijos:
        lineas.extend(lineas_instruccion(instruccion, nivel + 1))

    lineas.append(f"{sangria}}}")
    return lineas


def lineas_instruccion(nodo, nivel):
    sangria = "    " * nivel

    if nodo.tipo == "declaracion":
        datos = nodo.valor
        prefijo = "constante " if datos.get("constante") else ""
        texto = f"{sangria}{prefijo}{datos.get('tipo')} {datos.get('nombre')}"
        if nodo.hijos:
            texto += f" = {formatear_expresion(nodo.hijos[0])}"
        return [texto + ";"]

    if nodo.tipo == "asignacion":
        return [f"{sangria}{nodo.valor} = {formatear_expresion(nodo.hijos[0])};"]

    if nodo.tipo == "si":
        condicion, bloque_si, *bloques_sino = nodo.hijos
        encabezado = f"si ({formatear_expresion(condicion)})"
        lineas = lineas_bloque(bloque_si, nivel, encabezado)
        if bloques_sino:
            lineas[-1] = f"{sangria}}} sino {{"
            lineas.extend(lineas_bloque(bloques_sino[0], nivel)[1:])
        return lineas

    if nodo.tipo == "mientras":
        condicion, cuerpo = nodo.hijos
        encabezado = f"mientras ({formatear_expresion(condicion)})"
        return lineas_bloque(cuerpo, nivel, encabezado)

    if nodo.tipo == "bloque":
        return lineas_bloque(nodo, nivel)

    if nodo.tipo == "retornar":
        return [f"{sangria}retornar {formatear_expresion(nodo.hijos[0])};"]

    if nodo.tipo == "mostrar":
        argumentos = ", ".join(
            hijo.valor if hijo.tipo == "cadena" else formatear_expresion(hijo)
            for hijo in nodo.hijos
        )
        return [f"{sangria}mostrar({argumentos});"]

    if nodo.tipo in ("romper", "continuar"):
        return [f"{sangria}{nodo.tipo};"]

    return [f"{sangria}/* nodo no soportado: {nodo.tipo} */"]


def generar_codigo(arbol):
    principal = arbol.hijos[0] if arbol.hijos else None
    if principal is None:
        return ""

    bloque = principal.hijos[0] if principal.hijos else None
    if bloque is None:
        return "entero principal() {\n}\n"
    lineas = lineas_bloque(bloque, 0, "entero principal()")
    return "\n".join(lineas) + "\n"


class GeneradorIntermedio:
    def __init__(self, tabla):
        self.lineas = []
        self.temporales = 0
        self.etiquetas = {}
        self.ciclos = []
        self.tabla = tabla

    def generar(self, arbol):
        self.lineas.append("func principal")
        for registro in self.tabla.registros:
            clase = "decl" if registro["modificable"] else "const"
            self.emitir(f"{clase} {registro['tipo']} @{registro['nombre']}")
        self.bloque(arbol.hijos[0].hijos[0])
        self.lineas.append("endfunc")
        return "\n".join(self.lineas) + "\n"

    def emitir(self, texto):
        self.lineas.append(f"    {texto}")

    def etiqueta(self, nombre):
        numero = len(self.etiquetas) + 1
        etiqueta = f"%L{numero}"
        self.etiquetas[etiqueta] = f".L{nombre}_{numero}"
        return etiqueta

    def marcar(self, etiqueta):
        self.lineas.append(f"{etiqueta}:")

    def calcular(self, operacion):
        self.temporales += 1
        temporal = f"%t{self.temporales}"
        self.emitir(f"{temporal} = {operacion}")
        return temporal

    def operandos(self, nodo):
        izquierda, derecha = nodo.hijos
        destino = "decimal" if "decimal" in (izquierda.tipo_dato, derecha.tipo_dato) else None
        return self.expresion(izquierda, destino), self.expresion(derecha, destino)

    def expresion(self, nodo, destino=None):
        if nodo.tipo == "literal":
            valor = valor_texto(nodo.valor[1])
        elif nodo.tipo == "identificador":
            valor = f"@{nodo.valor}"
        elif nodo.tipo == "cadena":
            valor = json.dumps(nodo.valor[1:-1])
        elif nodo.tipo == "binaria":
            izquierda, derecha = self.operandos(nodo)
            valor = self.calcular(f"{izquierda} {nodo.valor} {derecha}")
        else:
            raise ValueError(f"Expresión intermedia no soportada: {nodo.tipo}")

        if destino == "decimal" and nodo.tipo_dato == "entero":
            return self.calcular(f"decimal {valor}")
        return valor

    def condicion(self, nodo, verdadero, falso):
        if nodo.tipo == "negacion":
            self.condicion(nodo.hijos[0], falso, verdadero)
        elif nodo.tipo == "logica":
            izquierda, derecha = nodo.hijos
            siguiente = self.etiqueta("evaluar_derecha")
            if nodo.valor == "&&":
                self.condicion(izquierda, siguiente, falso)
            else:
                self.condicion(izquierda, verdadero, siguiente)
            self.marcar(siguiente)
            self.condicion(derecha, verdadero, falso)
        elif nodo.tipo == "comparacion":
            izquierda, derecha = self.operandos(nodo)
            self.emitir(f"if {izquierda} {nodo.valor} {derecha} goto {verdadero}")
            self.emitir(f"goto {falso}")
        else:
            raise ValueError(f"Condición intermedia no soportada: {nodo.tipo}")

    def bloque(self, nodo):
        for instruccion in nodo.hijos:
            self.instruccion(instruccion)

    def instruccion(self, nodo):
        tipo = nodo.tipo
        if tipo == "declaracion":
            if nodo.hijos:
                nombre = nodo.valor["nombre"]
                valor = self.expresion(nodo.hijos[0], nodo.valor["tipo"])
                self.emitir(f"init @{nombre}, {valor}")
        elif tipo == "asignacion":
            destino = self.tabla.buscar(nodo.valor)["tipo"]
            valor = self.expresion(nodo.hijos[0], destino)
            self.emitir(f"@{nodo.valor} = {valor}")
        elif tipo == "bloque":
            self.bloque(nodo)
        elif tipo == "si":
            self.decision(nodo)
        elif tipo == "mientras":
            self.ciclo(nodo)
        elif tipo == "romper":
            self.emitir(f"goto {self.ciclos[-1][1]}")
        elif tipo == "continuar":
            self.emitir(f"goto {self.ciclos[-1][0]}")
        elif tipo == "retornar":
            self.emitir(f"return {self.expresion(nodo.hijos[0])}")
        elif tipo == "mostrar":
            argumentos = [self.expresion(hijo) for hijo in nodo.hijos]
            for argumento in argumentos:
                self.emitir(f"param {argumento}")
            self.emitir(f"call mostrar, {len(argumentos)}")
        else:
            raise ValueError(f"Instrucción intermedia no soportada: {tipo}")

    def decision(self, nodo):
        condicion, bloque_si, *bloques_sino = nodo.hijos
        verdadero, fin = self.etiqueta("si"), self.etiqueta("fin_si")
        falso = self.etiqueta("sino") if bloques_sino else fin
        self.condicion(condicion, verdadero, falso)
        self.marcar(verdadero)
        self.bloque(bloque_si)
        if bloques_sino:
            self.emitir(f"goto {fin}")
            self.marcar(falso)
            self.bloque(bloques_sino[0])
        self.marcar(fin)

    def ciclo(self, nodo):
        condicion, cuerpo = nodo.hijos
        inicio = self.etiqueta("probar_ciclo")
        ejecutar = self.etiqueta("cuerpo_ciclo")
        fin = self.etiqueta("fin_ciclo")
        self.marcar(inicio)
        self.condicion(condicion, ejecutar, fin)
        self.marcar(ejecutar)
        self.ciclos.append((inicio, fin))
        self.bloque(cuerpo)
        self.ciclos.pop()
        self.emitir(f"goto {inicio}")
        self.marcar(fin)


def generar_intermedio(arbol, tabla):
    return GeneradorIntermedio(tabla).generar(arbol)


class GeneradorEnsamblador:
    SALTOS = {
        "==": ("je", "je"), "!=": ("jne", "jne"), "<": ("jl", "jb"),
        "<=": ("jle", "jbe"), ">": ("jg", "ja"), ">=": ("jge", "jae"),
    }
    OPERACIONES = {
        "+": ("add", "addsd"), "-": ("sub", "subsd"),
        "*": ("imul", "mulsd"), "/": ("idiv", "divsd"),
    }
    FORMATOS = {"entero": "%ld", "decimal": "%.15g", "caracter": "%s"}
    REGISTROS_ENTEROS = ("rsi", "rdx", "rcx", "r8", "r9")

    def __init__(self, etiquetas=None):
        self.lineas = []
        self.ranuras = {}
        self.datos = {}
        self.argumentos = []
        self.etiquetas = etiquetas or {}

    def emitir(self, *instrucciones):
        self.lineas.extend(f"    {texto}" for texto in instrucciones)

    def nombre_etiqueta(self, salto):
        return self.etiquetas.get(salto, f".Lsalto_{salto[2:]}")

    def dato(self, directiva, nombre):
        etiqueta = self.datos.setdefault(directiva, f".L{nombre}_{len(self.datos) + 1}")
        return f"[rip + {etiqueta}]"

    def texto(self, texto, nombre):
        partes = []
        for caracter in texto:
            if caracter == "\n":
                partes.append(r"\n")
            elif caracter in '\\"':
                partes.append("\\" + caracter)
            elif caracter.isprintable():
                partes.append(caracter)
            else:
                partes.extend(f"\\{byte:03o}" for byte in caracter.encode("utf-8"))
        return self.dato(f'.asciz "{"".join(partes)}"', nombre)

    def reservar(self, nombre, tipo):
        if nombre not in self.ranuras:
            simbolo = f".Lvar_{nombre[1:]}" if nombre.startswith("@") else f".Ltemporal_{nombre[2:]}"
            self.ranuras[nombre] = (tipo, simbolo)
        return f"[rbp + {self.ranuras[nombre][1]}]"

    def tipo(self, valor):
        if valor in self.ranuras:
            return self.ranuras[valor][0]
        if valor.startswith("'"):
            return "caracter"
        return "decimal" if "." in valor else "entero"

    def cargar(self, valor, entero="rax", decimal="xmm0"):
        tipo = self.tipo(valor)
        if valor in self.ranuras:
            origen = self.reservar(valor, tipo)
            mover, registro = ("movsd", decimal) if tipo == "decimal" else ("mov", entero)
            if self.lineas[-1:] == [f"    {mover} {origen}, {registro}"]:
                if valor.startswith("%t") and self.usos[valor] == 2:
                    self.lineas.pop()
                    del self.ranuras[valor]
                return tipo
            instruccion = f"{mover} {registro}, {origen}"
        elif tipo == "caracter":
            instruccion = f"lea {entero}, {self.texto(valor[1:-1], 'caracter')}"
        elif tipo == "decimal":
            numero = float(valor)
            dato = ".quad 0x7ff0000000000000" if numero == float("inf") else f".double {numero!r}"
            instruccion = f"movsd {decimal}, {self.dato(dato, 'decimal')}"
        else:
            numero = (int(valor) + (1 << 63)) % (1 << 64) - (1 << 63)
            instruccion = f"mov {entero}, {numero}"
        self.emitir(instruccion)
        return tipo

    def cargar_pareja(self, izquierda, derecha):
        tipo = self.cargar(izquierda)
        self.cargar(derecha, "rcx", "xmm1")
        return tipo == "decimal"

    def asignar(self, destino, expresion):
        partes = expresion.split()
        if len(partes) == 1 and expresion.isdecimal() and int(expresion) < 2 ** 31:
            direccion = self.reservar(destino, "entero")
            self.emitir(f"mov QWORD PTR {direccion}, {int(expresion)}")
            return
        if len(partes) == 1:
            tipo = self.cargar(partes[0])
        elif partes[0] == "decimal":
            self.cargar(partes[1])
            self.emitir("cvtsi2sd xmm0, rax")
            tipo = "decimal"
        else:
            izquierda, operador, derecha = partes
            decimal = self.cargar_pareja(izquierda, derecha)
            tipo = "decimal" if decimal else "entero"
            entero, flotante = self.OPERACIONES[operador]
            if decimal:
                self.emitir(f"{flotante} xmm0, xmm1")
            elif operador == "/":
                self.emitir("cmp rcx, -1", "jne 1f", "neg rax", "jmp 2f",
                            "1:", "cqo", "idiv rcx", "2:")
            else:
                self.emitir(f"{entero} rax, rcx")

        direccion = self.reservar(destino, tipo)
        self.emitir(f"movsd {direccion}, xmm0" if tipo == "decimal" else f"mov {direccion}, rax")

    def comparar(self, izquierda, operador, derecha, salto):
        decimal = self.cargar_pareja(izquierda, derecha)
        destino = self.nombre_etiqueta(salto)
        self.emitir("ucomisd xmm0, xmm1" if decimal else "cmp rax, rcx")
        saltar_nan = decimal and operador in ("==", "<", "<=")
        if saltar_nan:
            self.emitir("jp 1f")
        if decimal and operador == "!=":
            self.emitir(f"jp {destino}")
        self.emitir(f"{self.SALTOS[operador][decimal]} {destino}")
        if saltar_nan:
            self.emitir("1:")

    def imprimir_grupo(self, formato, enteros, decimales):
        if not formato:
            return
        for registro, valor in zip(self.REGISTROS_ENTEROS, enteros):
            self.cargar(valor, entero=registro)
        for indice, valor in enumerate(decimales):
            self.cargar(valor, decimal=f"xmm{indice}")
        destino = self.texto("".join(formato), "formato_mostrar")
        self.emitir(f"lea rdi, {destino}", f"mov eax, {len(decimales)}", "call printf@PLT")
        formato.clear()
        enteros.clear()
        decimales.clear()

    def mostrar(self):
        formato, enteros, decimales = [], [], []
        for valor in self.argumentos:
            if valor.startswith('"'):
                for indice, texto in enumerate(json.loads(valor).split("\0")):
                    if indice:
                        self.imprimir_grupo(formato, enteros, decimales)
                        self.emitir("xor edi, edi", "call putchar@PLT")
                    formato.append(texto.replace("%", "%%"))
                continue

            tipo = self.tipo(valor)
            grupo, limite = (decimales, 8) if tipo == "decimal" else (enteros, len(self.REGISTROS_ENTEROS))
            if len(grupo) == limite:
                self.imprimir_grupo(formato, enteros, decimales)
            grupo.append(valor)
            formato.append(self.FORMATOS[tipo])
        formato.append("\n")
        self.imprimir_grupo(formato, enteros, decimales)
        self.argumentos.clear()

    def traducir(self, linea):
        op, _, resto = linea.partition(" ")
        if op in ("decl", "const"):
            tipo, nombre = resto.split()
            direccion = self.reservar(nombre, tipo)
            if nombre in self.inicializados:
                return
            if tipo == "caracter":
                self.emitir(f"lea rax, {self.texto('', 'caracter_vacio')}", f"mov {direccion}, rax")
            else:
                self.emitir(f"mov QWORD PTR {direccion}, 0")
        elif op == "init":
            self.asignar(*resto.split(", ", 1))
        elif op == "if":
            izquierda, operador, derecha, _, salto = resto.split()
            self.comparar(izquierda, operador, derecha, salto)
        elif op == "goto":
            self.emitir(f"jmp {self.nombre_etiqueta(resto)}")
        elif op.startswith("%L"):
            self.lineas.append(f"{self.nombre_etiqueta(op[:-1])}:")
        elif op == "param":
            self.argumentos.append(resto)
        elif op == "call":
            self.mostrar()
        elif op == "return":
            self.cargar(resto)
            self.emitir("jmp .Lfin_ce")
        else:
            self.asignar(*linea.split(" = ", 1))

    def generar(self, intermedio, *, tabla=None):
        lineas = intermedio.splitlines()[1:-1]
        self.usos = Counter(" ".join(lineas).split())
        self.inicializados = set()
        for linea in lineas:
            op, _, resto = linea.strip().partition(" ")
            if op in ("if", "goto", "return") or op.startswith("%L"):
                break
            if op == "init":
                self.inicializados.add(resto.split(",", 1)[0])
        for linea in lineas:
            self.traducir(linea.strip())

        encabezado = [".intel_syntax noprefix"]
        for indice, (nombre, (_, simbolo)) in enumerate(self.ranuras.items(), 1):
            desplazamiento = -8 * indice
            encabezado.append(f".equ {simbolo}, {desplazamiento}")
            if tabla is not None and nombre.startswith("@"):
                tabla.buscar(nombre[1:])["almacenamiento"] = desplazamiento
        encabezado.extend(["", ".text", ".globl main", "main:", "    push rbp", "    mov rbp, rsp"])
        espacio = (len(self.ranuras) + 1) // 2 * 16
        if espacio:
            encabezado.append(f"    sub rsp, {espacio}")
        if self.lineas[-1:] == ["    jmp .Lfin_ce"]:
            self.lineas.pop()
        else:
            self.emitir("xor eax, eax")
        self.lineas.extend([".Lfin_ce:", "    leave", "    ret"])
        if self.datos:
            self.lineas.extend(["", ".section .rodata"])
            for directiva, etiqueta in self.datos.items():
                self.lineas.append(f"{etiqueta}: {directiva}")
        self.lineas.append('.section .note.GNU-stack,"",@progbits')
        return "\n".join(encabezado + self.lineas) + "\n"


def generar_ensamblador(intermedio, etiquetas=None, *, tabla=None):
    return GeneradorEnsamblador(etiquetas).generar(intermedio, tabla=tabla)


def contenido_simbolos(nombre, tabla):
    contenido = tabla_simbolos_texto(tabla) or "(SIN SÍMBOLOS)"
    partes = ["TABLA DE SÍMBOLOS - COMPILADOR CE", f"ARCHIVO: {nombre}", "", contenido]
    referencias = referencias_texto(tabla)
    if referencias:
        partes.extend(["", "REFERENCIAS POR SÍMBOLO", referencias])
    return "\n".join(partes) + "\n"


def agregar_seccion(partes, titulo, contenido):
    partes.extend(["", titulo, "=" * len(titulo), contenido])


def contenido_reporte(nombre, tokens, estado, *, arbol=None, tabla=None,
                      errores_lexicos=(), errores_sintacticos=(), errores_semanticos=()):
    etapas = ["LÉXICO"]
    if arbol is not None:
        etapas.append("SINTÁCTICO")
    if tabla is not None:
        etapas.append("SEMÁNTICO")

    partes = [
        "REPORTE DE ANÁLISIS - COMPILADOR CE",
        f"ARCHIVO: {nombre}",
        f"ESTADO: {estado}",
        f"ETAPAS EJECUTADAS: {', '.join(etapas)}",
        f"TOKENS: {len(tokens)}",
        f"ERRORES LÉXICOS: {len(errores_lexicos)}",
        f"ERRORES SINTÁCTICOS: {len(errores_sintacticos)}",
        f"ERRORES SEMÁNTICOS: {len(errores_semanticos)}",
    ]

    agregar_seccion(partes, "TOKENS", tabla_tokens_texto(tokens))
    if errores_lexicos:
        agregar_seccion(partes, "ERRORES LÉXICOS", texto_errores(errores_lexicos))
    if arbol is not None:
        agregar_seccion(partes, "ÁRBOL SINTÁCTICO", arbol_dibujado_texto(arbol))
    if errores_sintacticos:
        agregar_seccion(partes, "ERRORES SINTÁCTICOS", texto_errores(errores_sintacticos))
    if tabla is not None:
        agregar_seccion(partes, "TABLA DE SÍMBOLOS", tabla_simbolos_texto(tabla) or "(SIN SÍMBOLOS)")
        referencias = referencias_texto(tabla)
        if referencias:
            agregar_seccion(partes, "REFERENCIAS POR SÍMBOLO", referencias)
    if errores_semanticos:
        agregar_seccion(partes, "ERRORES SEMÁNTICOS", texto_errores(errores_semanticos))

    return "\n".join(partes) + "\n"
