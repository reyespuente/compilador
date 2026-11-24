import ast as ast_mod
import csv
import os
import sys
import textwrap
from dataclasses import dataclass, field
from decimal import Decimal
from typing import NamedTuple

ARCHIVO_DEFINICIONES = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "DEFINICIONES.TXT"
)
ARCHIVO_MATRIZ = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "MATRIZ_TRANSICION.csv"
)
ESTADO_INICIAL = "q0"
ESTADO_RECHAZO = "q_error"

CLASE_POR_CARACTER = {
    **{c: c for c in "abcdefghijklmnopqrstuvwxyz"},
    **{c: "OTRA_LETRA" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZáéíóúüñÁÉÍÓÚÜÑ"},
    **{c: "DIGITO" for c in "0123456789"},
    **{c: "ARITMETICO" for c in "+-*/%"},
    **{c: "ESPACIO_TAB" for c in " \t"},
    "_": "GUION_BAJO",
    ".": "PUNTO",
    "'": "COMILLA_SIMPLE",
    '"': "COMILLA_DOBLE",
    "=": "IGUAL",
    "!": "ADMIRACION",
    "<": "MENOR",
    ">": "MAYOR",
    "&": "AMPERSAND",
    "|": "BARRA_VERTICAL",
    "(": "PAR_IZQ",
    ")": "PAR_DER",
    "{": "LLAVE_IZQ",
    "}": "LLAVE_DER",
    ";": "PUNTO_COMA",
    ",": "COMA",
    ":": "DOS_PUNTOS",
    "\r": "CR",
    "\n": "LF",
}
CLASES_ENTRADA = set(CLASE_POR_CARACTER.values()) | {"OTRO"}


class Token(NamedTuple):
    tipo: str
    lexema: str
    linea: int
    columna: int


class ErrorCompilacion(NamedTuple):
    codigo: int
    mensaje: str
    fase: str
    lexema: str
    linea: int
    columna: int


@dataclass
class Nodo:
    tipo: str
    linea: int
    columna: int
    valor: object = None
    hijos: list = field(default_factory=list)
    id_simbolo: int | None = None


def _leer_secciones(ruta):
    secciones = {}
    actual = None

    with open(ruta, encoding="utf-8") as archivo:
        for numero, linea in enumerate(archivo, 1):
            limpia = linea.rstrip("\r\n")
            if not limpia.strip() or limpia.lstrip().startswith("#"):
                continue

            if limpia.startswith("[") and limpia.endswith("]"):
                actual = limpia[1:-1].strip().upper()
                if not actual:
                    raise ValueError(f"LÍNEA {numero}: SECCIÓN VACÍA")
                secciones.setdefault(actual, [])
                continue

            if actual is None:
                raise ValueError(
                    f"LÍNEA {numero}: CONTENIDO FUERA DE UNA SECCIÓN"
                )

            secciones[actual].append((numero, limpia))

    return secciones


def _valor_config(secciones, clave):
    for numero, linea in secciones.get("CONFIG", []):
        nombre, separador, valor = linea.partition("=")
        if separador and nombre.strip().upper() == clave:
            valor = valor.strip()
            if (
                len(valor) >= 2
                and valor[0] == valor[-1]
                and valor[0] in "'\""
            ):
                valor = valor[1:-1]
            return valor

    raise ValueError(f"FALTA LA CLAVE {clave} EN [CONFIG]")


def cargar_definiciones(ruta):
    secciones = _leer_secciones(ruta)

    requeridas = ("CONFIG", "COLORES", "MENSAJES", "ERRORES")
    faltantes = [nombre for nombre in requeridas if nombre not in secciones]
    if faltantes:
        raise ValueError("FALTAN SECCIONES: " + ", ".join(faltantes))

    config = {
        "EXTENSION": _valor_config(secciones, "EXTENSION"),
        "ANCHO_TAB": int(_valor_config(secciones, "ANCHO_TAB")),
        "ARCHIVO_SIMBOLOS": _valor_config(secciones, "ARCHIVO_SIMBOLOS"),
        "ARCHIVO_ANALISIS": _valor_config(secciones, "ARCHIVO_ANALISIS"),
        "ARCHIVO_REPORTE": _valor_config(secciones, "ARCHIVO_REPORTE"),
        "ARCHIVO_ARBOL": _valor_config(secciones, "ARCHIVO_ARBOL"),
    }

    colores = {}
    for numero, linea in secciones["COLORES"]:
        nombre, separador, valor = linea.partition("=")
        if not separador:
            raise ValueError(
                f"LÍNEA {numero}: SE ESPERABA NOMBRE = \"valor\""
            )
        try:
            colores[nombre.strip().upper()] = ast_mod.literal_eval(
                valor.strip()
            )
        except (ValueError, SyntaxError) as exc:
            raise ValueError(
                f"LÍNEA {numero}: COLOR INVÁLIDO ({exc})"
            ) from exc

    mensajes = {}
    for numero, linea in secciones["MENSAJES"]:
        grupo, separador, codigo = linea.partition("=")
        if not separador:
            raise ValueError(
                f"LÍNEA {numero}: SE ESPERABA GRUPO = CÓDIGO"
            )
        mensajes[grupo.strip().upper()] = int(codigo.strip())

    errores = {}
    for numero, linea in secciones["ERRORES"]:
        codigo, separador, mensaje = linea.partition("=")
        if not separador:
            raise ValueError(
                f"LÍNEA {numero}: SE ESPERABA CÓDIGO = MENSAJE"
            )
        errores[int(codigo.strip())] = mensaje.strip()

    for grupo, codigo in mensajes.items():
        if codigo not in errores:
            raise ValueError(
                f"FALTA EL MENSAJE {codigo} DE {grupo} EN [ERRORES]"
            )

    return {
        "config": config,
        "colores": colores,
        "mensajes": mensajes,
        "errores": errores,
    }


def cargar_matriz(ruta, mensajes):
    estados = {}
    with open(ruta, encoding="utf-8-sig", newline="") as archivo:
        lector = csv.reader(archivo, delimiter=";", strict=True)
        encabezado = next(lector, [])
        clases = encabezado[2:]
        if (
            encabezado[:2] != ["ESTADO", "RESULTADO"]
            or set(clases) != CLASES_ENTRADA
            or len(clases) != len(CLASES_ENTRADA)
        ):
            raise ValueError("ENCABEZADO O CLASES DE ENTRADA INVÁLIDOS")

        for fila in lector:
            if not fila:
                continue
            if len(fila) != len(encabezado):
                raise ValueError(f"FILA {lector.line_num}: NÚMERO DE COLUMNAS INVÁLIDO")
            estado, resultado, *destinos = fila
            if not estado or estado in estados:
                raise ValueError(f"FILA {lector.line_num}: ESTADO VACÍO O REPETIDO")
            if resultado.startswith("ERROR_") and resultado not in mensajes:
                raise ValueError(f"ESTADO {estado}: ERROR SIN CÓDIGO ({resultado})")
            if not all(destinos):
                raise ValueError(f"ESTADO {estado}: HAY TRANSICIONES VACÍAS")
            estados[estado] = (resultado, dict(zip(clases, destinos)))

    if ESTADO_INICIAL not in estados or estados[ESTADO_INICIAL][0]:
        raise ValueError(f"{ESTADO_INICIAL} DEBE EXISTIR Y NO TENER RESULTADO")
    if estados.get(ESTADO_RECHAZO) != ("", dict.fromkeys(clases, ESTADO_RECHAZO)):
        raise ValueError(
            f"{ESTADO_RECHAZO} DEBE CARECER DE RESULTADO Y REGRESAR A SÍ MISMO"
        )
    for estado, (_, transiciones) in estados.items():
        for destino in transiciones.values():
            if destino not in estados:
                raise ValueError(f"ESTADO {estado}: DESTINO INEXISTENTE ({destino})")

    return estados


try:
    DEFINICIONES = cargar_definiciones(ARCHIVO_DEFINICIONES)
except (OSError, ValueError) as exc:
    print(f"ERROR AL CARGAR DEFINICIONES: {exc}", file=sys.stderr)
    sys.exit(2)

CONFIG = DEFINICIONES["config"]
EXTENSION = CONFIG["EXTENSION"]
ANCHO_TAB = CONFIG["ANCHO_TAB"]
COLORES = DEFINICIONES["colores"]

RESET = COLORES.get("RESET", "")
NEGRITA = COLORES.get("NEGRITA", "")
CIAN = COLORES.get("CIAN", "")
VERDE = COLORES.get("VERDE", "")
ROJO = COLORES.get("ROJO", "")
AMARILLO = COLORES.get("AMARILLO", "")
GRIS = COLORES.get("GRIS", "")

mensajes = DEFINICIONES["mensajes"]
ERRORES = DEFINICIONES["errores"]

try:
    MATRIZ_TRANSICION = cargar_matriz(ARCHIVO_MATRIZ, mensajes)
except (OSError, ValueError, csv.Error) as exc:
    print(f"ERROR AL CARGAR MATRIZ_TRANSICION.csv: {exc}", file=sys.stderr)
    sys.exit(2)

TIPOS_DATO = {
    "ENTERO": "entero",
    "DECIMAL": "decimal",
    "CARACTER": "caracter",
}

OPERADORES_RELACIONALES = {"==", "!=", "<", ">", "<=", ">="}

PRECEDENCIA = {
    "||": 1,
    "&&": 2,
    "==": 3, "!=": 3, "<": 3, ">": 3, "<=": 3, ">=": 3,
    "+": 4, "-": 4,
    "*": 5, "/": 5,
}


def avanzar_columna(columna, texto):
    for caracter in texto:
        if caracter == "\t":
            columna += ANCHO_TAB - (columna - 1) % ANCHO_TAB
        else:
            columna += 1
    return columna


def reconocer_lexema(codigo, inicio):
    _, transiciones = MATRIZ_TRANSICION[ESTADO_INICIAL]
    tipo = "ERROR_SIMBOLO"
    fin = inicio + 1

    # Conservar el último estado final permite distinguir, por ejemplo, < de <=.
    for pos in range(inicio, len(codigo)):
        clase = CLASE_POR_CARACTER.get(codigo[pos], "OTRO")
        destino = transiciones[clase]
        # El carácter que provocó el rechazo queda para el siguiente lexema.
        if destino == ESTADO_RECHAZO:
            break
        resultado, transiciones = MATRIZ_TRANSICION[destino]
        if resultado:
            tipo, fin = resultado, pos + 1

    return tipo, fin


def tokenizar(codigo):
    tokens = []
    errores = []
    linea = 1
    columna = 1

    inicio = 0
    while inicio < len(codigo):
        tipo, fin = reconocer_lexema(codigo, inicio)
        texto = codigo[inicio:fin]
        inicio = fin

        if tipo == "SALTO":
            linea += 1
            columna = 1
            continue

        if tipo in mensajes:
            codigo_error = mensajes[tipo]
            errores.append(ErrorCompilacion(
                codigo_error, ERRORES[codigo_error], "léxico",
                texto, linea, columna,
            ))
        elif tipo != "ESPACIO":
            tokens.append(Token(tipo, texto, linea, columna))

        columna = avanzar_columna(columna, texto)

    return tokens, errores


class Parser:
    def __init__(self, tokens):
        self.tokens = list(tokens)
        ultimo = self.tokens[-1] if self.tokens else Token("EOF", "", 1, 1)
        self.tokens.append(Token("EOF", "", ultimo.linea, ultimo.columna))
        self.pos = 0
        self.errores = []

    def actual(self):
        return self.tokens[self.pos]

    def tipo(self):
        return self.actual().tipo

    def lexema(self):
        return self.actual().lexema

    def avanzar(self):
        token = self.actual()
        if token.tipo != "EOF":
            self.pos += 1
        return token

    def error(self, codigo, token=None):
        token = token or self.actual()
        self.errores.append(ErrorCompilacion(
            codigo, ERRORES[codigo], "sintáctico",
            token.lexema, token.linea, token.columna,
        ))

    def esperar(self, tipo):
        if self.tipo() == tipo:
            return self.avanzar()
        self.error(202 if self.tipo() == "EOF" else 201)
        return None

    def programa(self):
        inicio = self.actual()
        self.esperar("ENTERO")
        self.esperar("PRINCIPAL")

        self.esperar("PAR_IZQ")
        self.esperar("PAR_DER")
        bloque = self.bloque()

        if self.tipo() != "EOF":
            self.error(201)

        principal = Nodo(
            "principal", inicio.linea, inicio.columna,
            hijos=[bloque] if bloque else [],
        )
        return Nodo(
            "programa", inicio.linea, inicio.columna,
            hijos=[principal],
        )

    def bloque(self):
        inicio = self.actual()
        if self.tipo() != "LLAVE_IZQ":
            self.error(202 if self.tipo() == "EOF" else 201)
            return Nodo("bloque", inicio.linea, inicio.columna)

        self.avanzar()
        hijos = []

        while self.tipo() not in ("LLAVE_DER", "EOF"):
            antes = self.pos
            instruccion = self.instruccion()
            if instruccion is not None:
                hijos.append(instruccion)

            if self.pos == antes:
                self.error(201)
                self.avanzar()

        if self.tipo() == "LLAVE_DER":
            self.avanzar()
        else:
            self.error(202)

        return Nodo("bloque", inicio.linea, inicio.columna, hijos=hijos)

    def instruccion(self):
        if self.tipo() in TIPOS_DATO or self.tipo() == "CONSTANTE":
            return self.declaracion()
        if self.tipo() == "ID":
            return self.asignacion()
        if self.tipo() == "SI":
            return self.decision()
        if self.tipo() == "MIENTRAS":
            return self.ciclo()
        if self.tipo() == "LLAVE_IZQ":
            return self.bloque()
        if self.tipo() == "RETORNAR":
            return self.retorno()
        if self.tipo() == "MOSTRAR":
            return self.mostrar()
        if self.tipo() in ("ROMPER", "CONTINUAR"):
            return self.control()

        return None

    def declaracion(self):
        inicio = self.actual()
        es_constante = self.tipo() == "CONSTANTE"
        if es_constante:
            self.avanzar()

        if self.tipo() in TIPOS_DATO:
            tipo = TIPOS_DATO[self.avanzar().tipo]
        else:
            self.error(201)
            tipo = None

        if self.tipo() == "ID":
            nombre = self.avanzar().lexema
        else:
            self.error(201)
            nombre = None

        expresion = None
        if self.tipo() == "OPERADOR" and self.lexema() == "=":
            self.avanzar()
            expresion = self.expresion()
        elif es_constante:
            self.error(201)

        self.esperar("PUNTO_COMA")

        return Nodo(
            "declaracion", inicio.linea, inicio.columna,
            valor={
                "tipo": tipo,
                "nombre": nombre,
                "constante": es_constante,
            },
            hijos=[expresion] if expresion is not None else [],
        )

    def asignacion(self):
        inicio = self.actual()
        nombre = self.avanzar().lexema

        if self.tipo() == "OPERADOR" and self.lexema() == "=":
            self.avanzar()
        else:
            self.error(201)

        expresion = self.expresion()
        self.esperar("PUNTO_COMA")

        return Nodo(
            "asignacion", inicio.linea, inicio.columna,
            valor=nombre, hijos=[expresion],
        )

    def decision(self):
        inicio = self.avanzar()
        self.esperar("PAR_IZQ")
        condicion = self.condicion()
        self.esperar("PAR_DER")
        bloque_si = self.bloque()

        hijos = [condicion, bloque_si]
        if self.tipo() == "SINO":
            self.avanzar()
            hijos.append(self.bloque())

        return Nodo("si", inicio.linea, inicio.columna, hijos=hijos)

    def ciclo(self):
        inicio = self.avanzar()
        self.esperar("PAR_IZQ")
        condicion = self.condicion()
        self.esperar("PAR_DER")
        cuerpo = self.bloque()

        return Nodo(
            "mientras", inicio.linea, inicio.columna,
            hijos=[condicion, cuerpo],
        )

    def retorno(self):
        inicio = self.avanzar()
        expresion = self.expresion()
        self.esperar("PUNTO_COMA")

        return Nodo(
            "retornar", inicio.linea, inicio.columna,
            hijos=[expresion],
        )

    def mostrar(self):
        inicio = self.avanzar()
        self.esperar("PAR_IZQ")
        argumentos = [self.argumento_mostrar()]
        while self.tipo() == "COMA":
            self.avanzar()
            argumentos.append(self.argumento_mostrar())
        self.esperar("PAR_DER")
        self.esperar("PUNTO_COMA")
        return Nodo(
            "mostrar", inicio.linea, inicio.columna, hijos=argumentos,
        )

    def argumento_mostrar(self):
        if self.tipo() == "LITERAL_CADENA":
            token = self.avanzar()
            return Nodo("cadena", token.linea, token.columna, valor=token.lexema)
        return self.expresion()

    def control(self):
        inicio = self.avanzar()
        self.esperar("PUNTO_COMA")

        return Nodo(inicio.tipo.lower(), inicio.linea, inicio.columna)

    def condicion(self):
        return self.o_logico()

    def o_logico(self):
        izquierda = self.y_logico()

        while self.tipo() == "OPERADOR" and self.lexema() == "||":
            operador = self.avanzar()
            derecha = self.y_logico()
            izquierda = Nodo(
                "logica", operador.linea, operador.columna,
                valor="||", hijos=[izquierda, derecha],
            )

        return izquierda

    def y_logico(self):
        izquierda = self.negacion()

        while self.tipo() == "OPERADOR" and self.lexema() == "&&":
            operador = self.avanzar()
            derecha = self.negacion()
            izquierda = Nodo(
                "logica", operador.linea, operador.columna,
                valor="&&", hijos=[izquierda, derecha],
            )

        return izquierda

    def negacion(self):
        if self.tipo() == "OPERADOR" and self.lexema() == "!":
            operador = self.avanzar()
            return Nodo(
                "negacion", operador.linea, operador.columna,
                hijos=[self.negacion()],
            )

        return self.comparacion()

    def comparacion(self):
        izquierda = self.expresion()

        if (
            self.tipo() == "OPERADOR"
            and self.lexema() in OPERADORES_RELACIONALES
        ):
            operador = self.avanzar()
            derecha = self.expresion()
            return Nodo(
                "comparacion", operador.linea, operador.columna,
                valor=operador.lexema, hijos=[izquierda, derecha],
            )

        return izquierda

    def expresion(self):
        izquierda = self.termino()

        while self.tipo() == "OPERADOR" and self.lexema() in ("+", "-"):
            operador = self.avanzar()
            derecha = self.termino()
            izquierda = Nodo(
                "binaria", operador.linea, operador.columna,
                valor=operador.lexema, hijos=[izquierda, derecha],
            )

        return izquierda

    def termino(self):
        izquierda = self.factor()

        while self.tipo() == "OPERADOR" and self.lexema() in ("*", "/"):
            operador = self.avanzar()
            derecha = self.factor()
            izquierda = Nodo(
                "binaria", operador.linea, operador.columna,
                valor=operador.lexema, hijos=[izquierda, derecha],
            )

        return izquierda

    def factor(self):
        token = self.actual()

        if token.tipo == "ID":
            self.avanzar()
            return Nodo(
                "identificador", token.linea, token.columna,
                valor=token.lexema,
            )

        if token.tipo == "NUMERO_ENTERO":
            self.avanzar()
            return Nodo(
                "literal", token.linea, token.columna,
                valor=("entero", int(token.lexema)),
            )

        if token.tipo == "NUMERO_DECIMAL":
            self.avanzar()
            return Nodo(
                "literal", token.linea, token.columna,
                valor=("decimal", Decimal(token.lexema)),
            )

        if token.tipo == "LITERAL_CARACTER":
            self.avanzar()
            return Nodo(
                "literal", token.linea, token.columna,
                valor=("caracter", token.lexema[1:-1]),
            )

        if token.tipo == "PAR_IZQ":
            self.avanzar()
            contenido = self.condicion()
            self.esperar("PAR_DER")
            return contenido

        self.error(201)
        return Nodo("error", token.linea, token.columna)


def analizar_sintactico(tokens):
    parser = Parser(tokens)
    arbol = parser.programa()
    return arbol, parser.errores


class TablaSimbolos:
    def __init__(self):
        self.simbolos = {}
        self.registros = []
        self.siguiente_id = 1

    def buscar(self, nombre):
        return self.simbolos.get(nombre)

    def existe(self, nombre):
        return nombre in self.simbolos

    def declarar(self, nombre, categoria, tipo, valor, modificable,
                 linea, columna):
        registro = {
            "id": self.siguiente_id,
            "nombre": nombre,
            "categoria": categoria,
            "tipo": tipo,
            "valor": valor,
            "modificable": modificable,
            "linea": linea,
            "columna": columna,
            "usos": [],
            "almacenamiento": None,
        }
        self.siguiente_id += 1
        self.simbolos[nombre] = registro
        self.registros.append(registro)
        return registro

    def registrar_uso(self, nombre, linea, columna):
        registro = self.buscar(nombre)
        if registro is not None:
            registro["usos"].append((linea, columna))


def compatible(destino, origen):
    return (
        destino == origen
        or (destino == "decimal" and origen == "entero")
    )


class AnalizadorSemantico:
    def __init__(self):
        self.tabla = TablaSimbolos()
        self.errores = []
        self.profundidad_ciclo = 0

    def error(self, codigo, nodo, detalle=""):
        self.errores.append(ErrorCompilacion(
            codigo, ERRORES[codigo], "semántico",
            detalle, nodo.linea, nodo.columna,
        ))

    def analizar(self, arbol):
        self.visitar(arbol)
        return self.tabla, self.errores

    def visitar(self, nodo):
        if nodo is None:
            return
        metodo = getattr(self, f"visitar_{nodo.tipo}", None)
        if metodo is not None:
            metodo(nodo)

    def visitar_programa(self, nodo):
        for hijo in nodo.hijos:
            self.visitar(hijo)

    def visitar_principal(self, nodo):
        bloque = nodo.hijos[0] if nodo.hijos else None
        if bloque is not None:
            for instruccion in bloque.hijos:
                self.visitar(instruccion)

    def visitar_bloque(self, nodo):
        for instruccion in nodo.hijos:
            self.visitar(instruccion)

    def visitar_declaracion(self, nodo):
        datos = nodo.valor
        nombre = datos.get("nombre")
        tipo = datos.get("tipo")
        if not nombre or not tipo:
            return

        if self.tabla.existe(nombre):
            self.error(302, nodo, nombre)
            return

        expresion = nodo.hijos[0] if nodo.hijos else None
        valor = None

        if expresion is not None:
            tipo_expresion = self.tipo_expresion(expresion)
            compatible_expresion = True
            if (
                tipo_expresion is not None
                and not compatible(tipo, tipo_expresion)
            ):
                self.error(306, nodo, nombre)
                compatible_expresion = False
            if compatible_expresion and expresion.tipo == "literal":
                valor = expresion.valor[1]

        registro = self.tabla.declarar(
            nombre,
            "CONSTANTE" if datos.get("constante") else "VARIABLE",
            tipo,
            valor,
            not datos.get("constante"),
            nodo.linea,
            nodo.columna,
        )
        nodo.id_simbolo = registro["id"]

    def visitar_asignacion(self, nodo):
        registro = self.tabla.buscar(nodo.valor)
        if registro is None:
            self.error(301, nodo, nodo.valor)
            return

        nodo.id_simbolo = registro["id"]
        self.tabla.registrar_uso(nodo.valor, nodo.linea, nodo.columna)

        expresion = nodo.hijos[0] if nodo.hijos else None
        if expresion is None:
            return

        tipo_expresion = self.tipo_expresion(expresion)

        if not registro["modificable"]:
            self.error(304, nodo, nodo.valor)
            return

        if (
            tipo_expresion is not None
            and not compatible(registro["tipo"], tipo_expresion)
        ):
            self.error(306, nodo, nodo.valor)

    def visitar_si(self, nodo):
        condicion = nodo.hijos[0]
        bloque_si = nodo.hijos[1]
        bloque_sino = nodo.hijos[2] if len(nodo.hijos) > 2 else None

        self.verificar_condicion(condicion)
        self.visitar_bloque(bloque_si)

        if bloque_sino is not None:
            self.visitar_bloque(bloque_sino)

    def visitar_mientras(self, nodo):
        condicion, cuerpo = nodo.hijos
        self.verificar_condicion(condicion)

        self.profundidad_ciclo += 1
        self.visitar_bloque(cuerpo)
        self.profundidad_ciclo -= 1

    def visitar_retornar(self, nodo):
        expresion = nodo.hijos[0] if nodo.hijos else None
        if expresion is None:
            return

        tipo = self.tipo_expresion(expresion)
        if tipo is not None and tipo != "entero":
            self.error(303, nodo, "retornar")

    def visitar_mostrar(self, nodo):
        for argumento in nodo.hijos:
            if argumento.tipo == "cadena":
                continue
            tipo = self.tipo_expresion(argumento)
            if tipo is not None and tipo not in TIPOS_DATO.values():
                self.error(303, argumento, "mostrar")

    def visitar_romper(self, nodo):
        if self.profundidad_ciclo == 0:
            self.error(305, nodo, "romper")

    def visitar_continuar(self, nodo):
        if self.profundidad_ciclo == 0:
            self.error(305, nodo, "continuar")

    def verificar_condicion(self, nodo):
        tipo = self.tipo_expresion(nodo)
        if tipo is not None and tipo != "logico":
            self.error(303, nodo, "condición")

    def tipo_expresion(self, nodo):
        if nodo is None:
            return None

        if nodo.tipo == "identificador":
            registro = self.tabla.buscar(nodo.valor)
            if registro is None:
                self.error(301, nodo, nodo.valor)
                return None
            nodo.id_simbolo = registro["id"]
            self.tabla.registrar_uso(nodo.valor, nodo.linea, nodo.columna)
            return registro["tipo"]

        if nodo.tipo == "literal":
            return nodo.valor[0]

        if nodo.tipo == "binaria":
            izquierda = self.tipo_expresion(nodo.hijos[0])
            derecha = self.tipo_expresion(nodo.hijos[1])
            if izquierda is None or derecha is None:
                return None

            numericos = ("entero", "decimal")
            if izquierda not in numericos or derecha not in numericos:
                self.error(303, nodo, nodo.valor)
                return None

            if "decimal" in (izquierda, derecha):
                return "decimal"
            return "entero"

        if nodo.tipo == "comparacion":
            izquierda = self.tipo_expresion(nodo.hijos[0])
            derecha = self.tipo_expresion(nodo.hijos[1])
            if izquierda is None or derecha is None:
                return None

            numericos = ("entero", "decimal")
            if nodo.valor in ("==", "!="):
                if izquierda in numericos and derecha in numericos:
                    return "logico"
                if izquierda == "caracter" and derecha == "caracter":
                    return "logico"
            else:
                if izquierda in numericos and derecha in numericos:
                    return "logico"

            self.error(303, nodo, nodo.valor)
            return None

        if nodo.tipo == "logica":
            izquierda = self.tipo_expresion(nodo.hijos[0])
            derecha = self.tipo_expresion(nodo.hijos[1])
            if izquierda is None or derecha is None:
                return None

            if izquierda == "logico" and derecha == "logico":
                return "logico"

            self.error(303, nodo, nodo.valor)
            return None

        if nodo.tipo == "negacion":
            tipo = self.tipo_expresion(nodo.hijos[0])
            if tipo is None:
                return None
            if tipo == "logico":
                return "logico"

            self.error(303, nodo, "!")
            return None

        return None


def analizar_semantico(arbol):
    analizador = AnalizadorSemantico()
    return analizador.analizar(arbol)


def formatear_tabla(encabezados, filas, alineaciones=None):
    if not filas:
        return ""

    columnas = len(encabezados)
    anchos = []
    for indice in range(columnas):
        valores = [str(fila[indice]) for fila in filas]
        valores.append(encabezados[indice])
        anchos.append(max(len(valor) for valor in valores))

    def linea(valores):
        partes = []
        for indice, valor in enumerate(valores):
            texto = str(valor)
            if alineaciones and alineaciones[indice] == "derecha":
                partes.append(texto.rjust(anchos[indice]))
            else:
                partes.append(texto.ljust(anchos[indice]))
        return "  ".join(partes).rstrip()

    resultado = [linea(encabezados)]
    resultado.extend(linea(fila) for fila in filas)
    return "\n".join(resultado)


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


def mostrar_tokens(tokens):
    print(tabla_tokens_texto(tokens))


def linea_error(error, color="", reset=""):
    detalle = f" ({error.lexema!r})" if error.lexema else ""
    return (
        f"{color}ERROR {error.codigo}{reset} EN "
        f"{error.linea}:{error.columna}: {error.mensaje}{detalle}"
    )


def texto_errores(errores):
    return "\n".join(linea_error(error) for error in errores) or "(SIN ERRORES)"


def mostrar_errores(titulo, errores):
    print()
    print(f"{ROJO}{titulo}{RESET}")
    for error in errores:
        print(linea_error(error, ROJO, RESET))


def recorrer_ast(nodo, nivel=0):
    yield nivel, nodo
    for hijo in nodo.hijos:
        if hijo is not None:
            yield from recorrer_ast(hijo, nivel + 1)


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


def dibujar_arbol(nodo, prefijo="", es_ultimo=True, es_raiz=True,
                  lineas=None):
    if lineas is None:
        lineas = []

    etiqueta = etiqueta_arbol(nodo)
    if es_raiz:
        lineas.append(etiqueta)
        extension = ""
    else:
        conector = "└── " if es_ultimo else "├── "
        lineas.append(prefijo + conector + etiqueta)
        extension = "    " if es_ultimo else "│   "

    hijos = [hijo for hijo in nodo.hijos if hijo is not None]
    nuevo_prefijo = prefijo + extension

    for indice, hijo in enumerate(hijos):
        dibujar_arbol(
            hijo,
            nuevo_prefijo,
            indice == len(hijos) - 1,
            False,
            lineas,
        )

    return lineas


def arbol_dibujado_texto(arbol):
    if arbol is None:
        return ""
    return "\n".join(dibujar_arbol(arbol))


def mostrar_arbol(arbol):
    texto = arbol_dibujado_texto(arbol)
    if texto:
        print(texto)
    else:
        print(f"{GRIS}(ÁRBOL VACÍO){RESET}")


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


def escribir_imagen_arbol(nombre, arbol):
    if arbol is None:
        return

    try:
        ruta = os.path.abspath(CONFIG["ARCHIVO_ARBOL"])
        generar_imagen_arbol(arbol, ruta, nombre)
        print(f"{GRIS}GENERADO: {ruta}{RESET}")
    except ImportError:
        print(
            f"{AMARILLO}IMAGEN NO GENERADA: INSTALA PILLOW "
            f"(pip install pillow){RESET}"
        )
    except (OSError, ValueError) as exc:
        print(
            f"{ROJO}NO SE PUDO GENERAR LA IMAGEN: {exc}{RESET}"
        )


def valor_texto(valor):
    if valor is None:
        return "SIN ASIGNAR"
    if isinstance(valor, str):
        return repr(valor)
    if isinstance(valor, Decimal):
        return format(valor, "f")
    return str(valor)


def almacenamiento_texto(registro):
    if registro["almacenamiento"] is None:
        return "PENDIENTE"
    return str(registro["almacenamiento"])


def tabla_simbolos_texto(tabla):
    filas = []
    for registro in tabla.registros:
        filas.append([
            str(registro["id"]),
            registro["nombre"],
            registro["categoria"],
            registro["tipo"],
            valor_texto(registro["valor"]),
            "SÍ" if registro["modificable"] else "NO",
            f"{registro['linea']}:{registro['columna']}",
            str(len(registro["usos"])),
            almacenamiento_texto(registro),
        ])

    return formatear_tabla(
        ["ID", "NOMBRE", "CATEGORÍA", "TIPO", "VALOR",
         "MOD", "LÍN:COL", "USOS", "UBICACIÓN"],
        filas,
        ["derecha", "izquierda", "izquierda", "izquierda",
         "izquierda", "izquierda", "derecha", "derecha",
         "izquierda"],
    )


def referencias_texto(tabla):
    filas = []
    for registro in tabla.registros:
        if not registro["usos"]:
            continue
        referencias = ", ".join(
            f"{linea}:{columna}" for linea, columna in registro["usos"]
        )
        filas.append([
            str(registro["id"]),
            registro["nombre"],
            referencias,
        ])

    return formatear_tabla(
        ["ID", "NOMBRE", "REFERENCIAS"],
        filas,
        ["derecha", "izquierda", "izquierda"],
    )


def mostrar_tabla_simbolos(tabla):
    texto = tabla_simbolos_texto(tabla)
    if texto:
        print(texto)
    else:
        print(f"{GRIS}(SIN SÍMBOLOS){RESET}")


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
        if precedencia < padre:
            return f"({texto})"
        return texto

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
        expresion = nodo.hijos[0] if nodo.hijos else None
        texto = (
            f"{sangria}"
            f"{'constante ' if datos.get('constante') else ''}"
            f"{datos.get('tipo')} {datos.get('nombre')}"
        )
        if expresion is not None:
            texto += f" = {formatear_expresion(expresion)}"
        return [texto + ";"]

    if nodo.tipo == "asignacion":
        return [
            f"{sangria}{nodo.valor} = "
            f"{formatear_expresion(nodo.hijos[0])};"
        ]

    if nodo.tipo == "si":
        condicion = nodo.hijos[0]
        bloque_si = nodo.hijos[1]
        bloque_sino = nodo.hijos[2] if len(nodo.hijos) > 2 else None

        encabezado = f"si ({formatear_expresion(condicion)})"
        lineas = lineas_bloque(bloque_si, nivel, encabezado)

        if bloque_sino is not None:
            lineas[-1] = f"{sangria}}} sino {{"
            lineas.extend(lineas_bloque(bloque_sino, nivel)[1:])

        return lineas

    if nodo.tipo == "mientras":
        condicion, cuerpo = nodo.hijos
        encabezado = f"mientras ({formatear_expresion(condicion)})"
        return lineas_bloque(cuerpo, nivel, encabezado)

    if nodo.tipo == "bloque":
        return lineas_bloque(nodo, nivel)

    if nodo.tipo == "retornar":
        return [
            f"{sangria}retornar "
            f"{formatear_expresion(nodo.hijos[0])};"
        ]

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


def contenido_simbolos(nombre, tabla):
    partes = [
        "TABLA DE SÍMBOLOS - COMPILADOR CE",
        f"ARCHIVO: {nombre}",
        "",
        tabla_simbolos_texto(tabla),
    ]

    referencias = referencias_texto(tabla)
    if referencias:
        partes.extend([
            "",
            "REFERENCIAS POR SÍMBOLO",
            referencias,
        ])

    return "\n".join(partes) + "\n"


def contenido_analisis(arbol):
    return generar_codigo(arbol)


def contenido_reporte(nombre, tokens, errores_lexicos, arbol,
                      errores_sintacticos, tabla, errores_semanticos,
                      estado):
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
        "",
        "TOKENS",
        "======",
        tabla_tokens_texto(tokens),
    ]

    if errores_lexicos:
        partes.extend([
            "",
            "ERRORES LÉXICOS",
            "===============",
            texto_errores(errores_lexicos),
        ])

    if arbol is not None:
        partes.extend([
            "",
            "ÁRBOL SINTÁCTICO",
            "================",
            arbol_dibujado_texto(arbol),
        ])

    if errores_sintacticos:
        partes.extend([
            "",
            "ERRORES SINTÁCTICOS",
            "===================",
            texto_errores(errores_sintacticos),
        ])

    if tabla is not None:
        partes.extend([
            "",
            "TABLA DE SÍMBOLOS",
            "=================",
            tabla_simbolos_texto(tabla),
        ])

        referencias = referencias_texto(tabla)
        if referencias:
            partes.extend([
                "",
                "REFERENCIAS POR SÍMBOLO",
                "=======================",
                referencias,
            ])

    if errores_semanticos:
        partes.extend([
            "",
            "ERRORES SEMÁNTICOS",
            "==================",
            texto_errores(errores_semanticos),
        ])

    return "\n".join(partes) + "\n"


def escribir_archivo(nombre, contenido):
    try:
        ruta = os.path.abspath(nombre)
        with open(ruta, "w", encoding="utf-8") as archivo:
            archivo.write(contenido)
        print(f"{GRIS}GENERADO: {ruta}{RESET}")
    except OSError as exc:
        print(f"{ROJO}NO SE PUDO ESCRIBIR {nombre}: {exc}{RESET}")


def eliminar_salidas():
    for clave in (
        "ARCHIVO_SIMBOLOS", "ARCHIVO_ANALISIS",
        "ARCHIVO_REPORTE", "ARCHIVO_ARBOL",
    ):
        try:
            os.remove(CONFIG[clave])
        except OSError:
            pass


def escribir_reporte(nombre, tokens, errores_lexicos, arbol,
                     errores_sintacticos, tabla, errores_semanticos,
                     estado):
    contenido = contenido_reporte(
        nombre, tokens, errores_lexicos, arbol,
        errores_sintacticos, tabla, errores_semanticos, estado,
    )
    escribir_archivo(CONFIG["ARCHIVO_REPORTE"], contenido)


def limpiar_ruta(texto):
    ruta = texto.strip()
    if len(ruta) >= 2 and ruta[0] == ruta[-1] and ruta[0] in "'\"":
        ruta = ruta[1:-1]
    ruta = ruta.replace("\\ ", " ")
    return os.path.expanduser(ruta)


def cargar_archivo(ruta):
    if not ruta.lower().endswith(EXTENSION.lower()):
        return None, (
            f"EL ARCHIVO DEBE TENER EXTENSIÓN {EXTENSION.upper()}"
        )

    try:
        with open(ruta, encoding="utf-8", newline="") as archivo:
            return archivo.read(), None
    except FileNotFoundError:
        return None, f"NO SE ENCONTRÓ EL ARCHIVO '{ruta}'"
    except UnicodeDecodeError:
        return None, (
            f"EL ARCHIVO '{ruta}' NO ESTÁ CODIFICADO EN UTF-8"
        )
    except OSError as exc:
        return None, f"NO SE PUDO LEER '{ruta}': {exc}"


def procesar_archivo(nombre, codigo):
    eliminar_salidas()

    print()
    print(f"{CIAN}ARCHIVO:{RESET} {nombre}")

    tokens, errores_lexicos = tokenizar(codigo)
    print(
        f"{CIAN}TOKENS:{RESET} {len(tokens)}    "
        f"{CIAN}ERRORES LÉXICOS:{RESET} {len(errores_lexicos)}"
    )
    print(GRIS + "-" * 72 + RESET)
    mostrar_tokens(tokens)

    if errores_lexicos:
        mostrar_errores("ERRORES LÉXICOS", errores_lexicos)
        print(f"{ROJO}EL ANÁLISIS SE DETIENE POR ERRORES LÉXICOS.{RESET}")
        escribir_reporte(
            nombre, tokens, errores_lexicos, None, [], None, [],
            "DETENIDO EN ANÁLISIS LÉXICO",
        )
        return 1

    arbol, errores_sintacticos = analizar_sintactico(tokens)

    if errores_sintacticos:
        mostrar_errores("ERRORES SINTÁCTICOS", errores_sintacticos)
        print(f"{ROJO}EL ANÁLISIS SE DETIENE POR ERRORES SINTÁCTICOS.{RESET}")
        escribir_reporte(
            nombre, tokens, errores_lexicos, arbol,
            errores_sintacticos, None, [],
            "DETENIDO EN ANÁLISIS SINTÁCTICO",
        )
        return 1

    tabla, errores_semanticos = analizar_semantico(arbol)
    escribir_imagen_arbol(nombre, arbol)

    print()
    print(f"{CIAN}ÁRBOL SINTÁCTICO{RESET}")
    mostrar_arbol(arbol)

    print()
    print(f"{CIAN}TABLA DE SÍMBOLOS{RESET}")
    mostrar_tabla_simbolos(tabla)

    escribir_archivo(CONFIG["ARCHIVO_SIMBOLOS"], contenido_simbolos(nombre, tabla))

    if errores_semanticos:
        mostrar_errores("ERRORES SEMÁNTICOS", errores_semanticos)
        print(
            f"{ROJO}COMPILACIÓN CON {len(errores_semanticos)} "
            f"ERROR(ES) SEMÁNTICO(S).{RESET}"
        )
        escribir_reporte(
            nombre, tokens, errores_lexicos, arbol,
            errores_sintacticos, tabla, errores_semanticos,
            "DETENIDO EN ANÁLISIS SEMÁNTICO",
        )
        return 1

    escribir_archivo(CONFIG["ARCHIVO_ANALISIS"], contenido_analisis(arbol))

    escribir_reporte(
        nombre, tokens, errores_lexicos, arbol,
        errores_sintacticos, tabla, errores_semanticos,
        "COMPILACIÓN CORRECTA",
    )

    print(f"{VERDE}COMPILACIÓN COMPLETADA SIN ERRORES.{RESET}")
    return 0


def limpiar_pantalla():
    print("\033[2J\033[H", end="")


def encabezado():
    print(
        f"{CIAN}{NEGRITA}COMPILADOR CE{RESET} "
        f"{GRIS}· ANÁLISIS LÉXICO, SINTÁCTICO Y SEMÁNTICO{RESET}"
    )
    print(GRIS + "-" * 60 + RESET)
    print(
        f"{GRIS}ARRASTRA O PEGA LA RUTA DE TU ARCHIVO "
        f"{EXTENSION.upper()}{RESET}"
    )
    print(
        f"{GRIS}GENERA {CONFIG['ARCHIVO_SIMBOLOS']}, "
        f"{CONFIG['ARCHIVO_ANALISIS']}{RESET}"
    )
    print(
        f"{GRIS}{CONFIG['ARCHIVO_REPORTE']} Y "
        f"{CONFIG['ARCHIVO_ARBOL']}{RESET}"
    )
    print(f"{GRIS}COMANDOS: SALIR, LIMPIAR, AYUDA{RESET}")
    print()


def modo_interactivo():
    limpiar_pantalla()
    encabezado()

    try:
        while True:
            entrada = input(f"{VERDE}CE>{RESET} ").strip()
            comando = entrada.lower()

            if not entrada:
                continue

            if comando in ("salir", "exit", "q"):
                return 0

            if comando in ("limpiar", "clear", "cls"):
                limpiar_pantalla()
                encabezado()
                continue

            if comando in ("ayuda", "help", "?"):
                print(
                    f"{AMARILLO}ARRASTRA TU ARCHIVO {EXTENSION.upper()} "
                    f"A LA TERMINAL O ESCRIBE SU RUTA.{RESET}"
                )
                print(
                    f"{AMARILLO}TAMBIÉN PUEDES USAR: "
                    f"PYTHON3 CE.py ARCHIVO.CE{RESET}"
                )
                print()
                continue

            ruta = limpiar_ruta(entrada)
            codigo, error = cargar_archivo(ruta)

            if error:
                print(f"{ROJO}ERROR:{RESET} {error}")
                print()
                continue

            procesar_archivo(os.path.basename(ruta), codigo)
            print()
    except (EOFError, KeyboardInterrupt):
        return 0


def main():
    if len(sys.argv) == 1:
        return modo_interactivo()

    if len(sys.argv) != 2:
        print("USO: PYTHON3 CE.py [ARCHIVO.CE]", file=sys.stderr)
        return 2

    ruta = limpiar_ruta(sys.argv[1])
    codigo, error = cargar_archivo(ruta)

    if error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    return procesar_archivo(os.path.basename(ruta), codigo)


if __name__ == "__main__":
    sys.exit(main())
