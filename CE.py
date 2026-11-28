import csv
import os
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from typing import NamedTuple

import salidas

CARPETA = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_DEFINICIONES = os.path.join(CARPETA, "DEFINICIONES.TXT")
ARCHIVO_MATRIZ = os.path.join(CARPETA, "MATRIZ_TRANSICION.csv")
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
    tipo_dato: str | None = None


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
    for _, linea in secciones["CONFIG"]:
        nombre, separador, valor = linea.partition("=")
        if separador and nombre.strip().upper() == clave:
            valor = valor.strip()
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
                return valor[1:-1]
            return valor

    raise ValueError(f"FALTA LA CLAVE {clave} EN [CONFIG]")


def _leer_pares(seccion, formato):
    for numero, linea in seccion:
        clave, separador, valor = linea.partition("=")
        if not separador:
            raise ValueError(f"LÍNEA {numero}: SE ESPERABA {formato}")
        yield numero, clave.strip(), valor.strip()


def cargar_definiciones(ruta):
    secciones = _leer_secciones(ruta)

    requeridas = ("CONFIG", "COLORES", "MENSAJES", "ERRORES")
    faltantes = [nombre for nombre in requeridas if nombre not in secciones]
    if faltantes:
        raise ValueError("FALTAN SECCIONES: " + ", ".join(faltantes))

    claves = ("EXTENSION", "ANCHO_TAB", "ARCHIVO_SIMBOLOS", "ARCHIVO_ANALISIS",
              "ARCHIVO_INTERMEDIO", "ARCHIVO_ENSAMBLADOR", "ARCHIVO_REPORTE", "ARCHIVO_ARBOL")
    config = {clave: _valor_config(secciones, clave) for clave in claves}
    config["ANCHO_TAB"] = int(config["ANCHO_TAB"])

    colores = {}
    for numero, nombre, codigo in _leer_pares(secciones["COLORES"], "NOMBRE = CÓDIGO ANSI"):
        if codigo and not all(p.isascii() and p.isdecimal() for p in codigo.split(";")):
            raise ValueError(f"LÍNEA {numero}: COLOR INVÁLIDO ({codigo})")
        colores[nombre.upper()] = f"\033[{codigo}m" if codigo else ""

    mensajes = {grupo.upper(): int(codigo) for _, grupo, codigo in
                _leer_pares(secciones["MENSAJES"], "GRUPO = CÓDIGO")}
    errores = {int(codigo): mensaje for _, codigo, mensaje in
               _leer_pares(secciones["ERRORES"], "CÓDIGO = MENSAJE")}

    for grupo, codigo in mensajes.items():
        if codigo not in errores:
            raise ValueError(f"FALTA EL MENSAJE {codigo} DE {grupo} EN [ERRORES]")

    return {"config": config, "colores": colores, "mensajes": mensajes, "errores": errores}


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

    for pos in range(inicio, len(codigo)):
        clase = CLASE_POR_CARACTER.get(codigo[pos], "OTRO")
        destino = transiciones[clase]
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


def nodo_en(token, tipo, valor=None, hijos=None):
    return Nodo(tipo, token.linea, token.columna, valor, [] if hijos is None else hijos)


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

        principal = nodo_en(inicio, "principal", hijos=[bloque])
        return nodo_en(inicio, "programa", hijos=[principal])

    def bloque(self):
        inicio = self.actual()
        if self.tipo() != "LLAVE_IZQ":
            self.error(202 if self.tipo() == "EOF" else 201)
            return nodo_en(inicio, "bloque")

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

        return nodo_en(inicio, "bloque", hijos=hijos)

    def instruccion(self):
        tipo = self.tipo()
        if tipo in TIPOS_DATO or tipo == "CONSTANTE":
            return self.declaracion()
        if tipo == "ID":
            return self.asignacion()
        if tipo in ("SI", "MIENTRAS"):
            return self.control_condicional()
        if tipo == "LLAVE_IZQ":
            return self.bloque()
        if tipo == "RETORNAR":
            return self.retorno()
        if tipo == "MOSTRAR":
            return self.mostrar()
        if tipo in ("ROMPER", "CONTINUAR"):
            return self.control()

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

        datos = {"tipo": tipo, "nombre": nombre, "constante": es_constante}
        hijos = [expresion] if expresion is not None else []
        return nodo_en(inicio, "declaracion", valor=datos, hijos=hijos)

    def asignacion(self):
        inicio = self.actual()
        nombre = self.avanzar().lexema

        if self.tipo() == "OPERADOR" and self.lexema() == "=":
            self.avanzar()
        else:
            self.error(201)

        expresion = self.expresion()
        self.esperar("PUNTO_COMA")

        return nodo_en(inicio, "asignacion", valor=nombre, hijos=[expresion])

    def control_condicional(self):
        inicio = self.avanzar()
        self.esperar("PAR_IZQ")
        condicion = self.condicion()
        self.esperar("PAR_DER")
        hijos = [condicion, self.bloque()]
        if inicio.tipo == "SI" and self.tipo() == "SINO":
            self.avanzar()
            hijos.append(self.bloque())
        return nodo_en(inicio, inicio.tipo.lower(), hijos=hijos)

    def retorno(self):
        inicio = self.avanzar()
        expresion = self.expresion()
        self.esperar("PUNTO_COMA")

        return nodo_en(inicio, "retornar", hijos=[expresion])

    def mostrar(self):
        inicio = self.avanzar()
        self.esperar("PAR_IZQ")
        argumentos = [self.argumento_mostrar()]
        while self.tipo() == "COMA":
            self.avanzar()
            argumentos.append(self.argumento_mostrar())
        self.esperar("PAR_DER")
        self.esperar("PUNTO_COMA")
        return nodo_en(inicio, "mostrar", hijos=argumentos)

    def argumento_mostrar(self):
        if self.tipo() == "LITERAL_CADENA":
            token = self.avanzar()
            return nodo_en(token, "cadena", valor=token.lexema)
        return self.expresion()

    def control(self):
        inicio = self.avanzar()
        self.esperar("PUNTO_COMA")

        return nodo_en(inicio, inicio.tipo.lower())

    def condicion(self):
        return self.o_logico()

    def o_logico(self):
        return self.operacion_repetida(self.y_logico(), self.y_logico, ("||",), "logica")

    def y_logico(self):
        return self.operacion_repetida(self.negacion(), self.negacion, ("&&",), "logica")

    def negacion(self):
        if self.tipo() == "OPERADOR" and self.lexema() == "!":
            operador = self.avanzar()
            return nodo_en(operador, "negacion", hijos=[self.negacion()])

        return self.comparacion()

    def comparacion(self):
        izquierda = self.expresion()

        if (
            self.tipo() == "OPERADOR"
            and self.lexema() in OPERADORES_RELACIONALES
        ):
            operador = self.avanzar()
            derecha = self.expresion()
            return nodo_en(operador, "comparacion", operador.lexema, [izquierda, derecha])

        return izquierda

    def expresion(self):
        return self.operacion_repetida(self.termino(), self.termino, ("+", "-"), "binaria")

    def termino(self):
        return self.operacion_repetida(self.factor(), self.factor, ("*", "/"), "binaria")

    def operacion_repetida(self, izquierda, leer_operando, operadores, tipo_nodo):
        while self.tipo() == "OPERADOR" and self.lexema() in operadores:
            operador = self.avanzar()
            derecha = leer_operando()
            izquierda = nodo_en(operador, tipo_nodo, operador.lexema, [izquierda, derecha])
        return izquierda

    def factor(self):
        token = self.actual()

        if token.tipo == "ID":
            self.avanzar()
            return nodo_en(token, "identificador", valor=token.lexema)

        if token.tipo == "NUMERO_ENTERO":
            self.avanzar()
            return nodo_en(token, "literal", valor=("entero", int(token.lexema)))

        if token.tipo == "NUMERO_DECIMAL":
            self.avanzar()
            return nodo_en(token, "literal", valor=("decimal", Decimal(token.lexema)))

        if token.tipo == "LITERAL_CARACTER":
            self.avanzar()
            return nodo_en(token, "literal", valor=("caracter", token.lexema[1:-1]))

        if token.tipo == "PAR_IZQ":
            self.avanzar()
            contenido = self.condicion()
            self.esperar("PAR_DER")
            return contenido

        self.error(201)
        return nodo_en(token, "error")


def analizar_sintactico(tokens):
    parser = Parser(tokens)
    arbol = parser.programa()
    return arbol, parser.errores


class TablaSimbolos:
    def __init__(self):
        self.simbolos = {}

    @property
    def registros(self):
        return self.simbolos.values()

    def buscar(self, nombre):
        return self.simbolos.get(nombre)

    def declarar(self, nombre, categoria, tipo, inicializador, modificable, linea, columna):
        registro = {
            "id": len(self.simbolos) + 1,
            "nombre": nombre,
            "categoria": categoria,
            "tipo": tipo,
            "inicializador": inicializador,
            "modificable": modificable,
            "linea": linea,
            "columna": columna,
            "usos": [],
            "almacenamiento": None,
        }
        self.simbolos[nombre] = registro
        return registro

    def registrar_uso(self, nombre, linea, columna):
        registro = self.buscar(nombre)
        if registro is not None:
            registro["usos"].append((linea, columna))


def compatible(destino, origen):
    return destino == origen or (destino == "decimal" and origen == "entero")


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
        if nodo.tipo in ("programa", "principal", "bloque"):
            for hijo in nodo.hijos:
                self.visitar(hijo)
            return
        if nodo.tipo in ("romper", "continuar"):
            if self.profundidad_ciclo == 0:
                self.error(305, nodo, nodo.tipo)
            return
        metodo = getattr(self, f"visitar_{nodo.tipo}", None)
        if metodo is not None:
            metodo(nodo)

    def visitar_declaracion(self, nodo):
        datos = nodo.valor
        nombre = datos.get("nombre")
        tipo = datos.get("tipo")
        if not nombre or not tipo:
            return

        if self.tabla.buscar(nombre) is not None:
            self.error(302, nodo, nombre)
            return

        expresion = nodo.hijos[0] if nodo.hijos else None
        if expresion is not None:
            tipo_expresion = self.tipo_expresion(expresion)
            if tipo_expresion is not None and not compatible(tipo, tipo_expresion):
                self.error(306, nodo, nombre)

        registro = self.tabla.declarar(
            nombre,
            "CONSTANTE" if datos.get("constante") else "VARIABLE",
            tipo,
            expresion,
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

        if tipo_expresion is not None and not compatible(registro["tipo"], tipo_expresion):
            self.error(306, nodo, nodo.valor)

    def visitar_si(self, nodo):
        condicion, *bloques = nodo.hijos
        self.verificar_condicion(condicion)
        for bloque in bloques:
            self.visitar(bloque)

    def visitar_mientras(self, nodo):
        condicion, cuerpo = nodo.hijos
        self.verificar_condicion(condicion)

        self.profundidad_ciclo += 1
        self.visitar(cuerpo)
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

    def verificar_condicion(self, nodo):
        tipo = self.tipo_expresion(nodo)
        if tipo is not None and tipo != "logico":
            self.error(303, nodo, "condición")

    def anotar_tipo(self, nodo, tipo):
        nodo.tipo_dato = tipo
        return tipo

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
            return self.anotar_tipo(nodo, registro["tipo"])

        if nodo.tipo == "literal":
            return self.anotar_tipo(nodo, nodo.valor[0])

        if nodo.tipo in ("binaria", "comparacion", "logica"):
            izquierda = self.tipo_expresion(nodo.hijos[0])
            derecha = self.tipo_expresion(nodo.hijos[1])
            if izquierda is None or derecha is None:
                return None

            tipos = (izquierda, derecha)
            numericos = all(tipo in ("entero", "decimal") for tipo in tipos)
            if nodo.tipo == "binaria" and numericos:
                tipo = "decimal" if "decimal" in tipos else "entero"
                return self.anotar_tipo(nodo, tipo)
            if nodo.tipo == "comparacion" and (
                numericos or (nodo.valor in ("==", "!=") and tipos == ("caracter", "caracter"))
            ):
                return self.anotar_tipo(nodo, "logico")
            if nodo.tipo == "logica" and tipos == ("logico", "logico"):
                return self.anotar_tipo(nodo, "logico")

            self.error(303, nodo, nodo.valor)
            return None

        if nodo.tipo == "negacion":
            tipo = self.tipo_expresion(nodo.hijos[0])
            if tipo is None:
                return None
            if tipo == "logico":
                return self.anotar_tipo(nodo, "logico")

            self.error(303, nodo, "!")
            return None

        return None


def analizar_semantico(arbol):
    return AnalizadorSemantico().analizar(arbol)


def mostrar_errores(titulo, errores):
    print(f"\n{ROJO}{titulo}{RESET}")
    for error in errores:
        print(salidas.linea_error(error, ROJO, RESET))


def escribir_imagen_arbol(nombre, arbol):
    if arbol is None:
        return

    try:
        ruta = os.path.abspath(CONFIG["ARCHIVO_ARBOL"])
        salidas.generar_imagen_arbol(arbol, ruta, nombre)
        print(f"{GRIS}GENERADO: {ruta}{RESET}")
    except ImportError:
        print(f"{AMARILLO}IMAGEN NO GENERADA: INSTALA PILLOW (pip install pillow){RESET}")
    except (OSError, ValueError) as exc:
        print(f"{ROJO}NO SE PUDO GENERAR LA IMAGEN: {exc}{RESET}")


def escribir_archivo(nombre, contenido):
    try:
        ruta = os.path.abspath(nombre)
        with open(ruta, "w", encoding="utf-8") as archivo:
            archivo.write(contenido)
        print(f"{GRIS}GENERADO: {ruta}{RESET}")
    except OSError as exc:
        print(f"{ROJO}NO SE PUDO ESCRIBIR {nombre}: {exc}{RESET}")


def eliminar_salidas():
    for clave, ruta in CONFIG.items():
        if clave.startswith("ARCHIVO_"):
            try:
                os.remove(ruta)
            except OSError:
                pass


def escribir_reporte(nombre, tokens, estado, **resultados):
    contenido = salidas.contenido_reporte(nombre, tokens, estado, **resultados)
    escribir_archivo(CONFIG["ARCHIVO_REPORTE"], contenido)


def limpiar_ruta(texto):
    ruta = texto.strip()
    if len(ruta) >= 2 and ruta[0] == ruta[-1] and ruta[0] in "'\"":
        ruta = ruta[1:-1]
    ruta = ruta.replace("\\ ", " ")
    return os.path.expanduser(ruta)


def cargar_archivo(ruta):
    if not ruta.lower().endswith(EXTENSION.lower()):
        return None, f"EL ARCHIVO DEBE TENER EXTENSIÓN {EXTENSION.upper()}"

    try:
        with open(ruta, encoding="utf-8", newline="") as archivo:
            return archivo.read(), None
    except FileNotFoundError:
        return None, f"NO SE ENCONTRÓ EL ARCHIVO '{ruta}'"
    except UnicodeDecodeError:
        return None, f"EL ARCHIVO '{ruta}' NO ESTÁ CODIFICADO EN UTF-8"
    except OSError as exc:
        return None, f"NO SE PUDO LEER '{ruta}': {exc}"


def procesar_archivo(nombre, codigo):
    eliminar_salidas()
    print(f"\n{CIAN}ARCHIVO:{RESET} {nombre}")
    tokens, errores_lexicos = tokenizar(codigo)
    print(
        f"{CIAN}TOKENS:{RESET} {len(tokens)}    "
        f"{CIAN}ERRORES LÉXICOS:{RESET} {len(errores_lexicos)}"
    )
    print(GRIS + "-" * 72 + RESET)
    print(salidas.tabla_tokens_texto(tokens))

    arbol, errores_sintacticos = (None, []) if errores_lexicos else analizar_sintactico(tokens)
    if errores_lexicos or errores_sintacticos:
        fase = "LÉXICO" if errores_lexicos else "SINTÁCTICO"
        mostrar_errores(f"ERRORES {fase}S", errores_lexicos or errores_sintacticos)
        print(f"{ROJO}EL ANÁLISIS SE DETIENE POR ERRORES {fase}S.{RESET}")
        escribir_reporte(
            nombre, tokens, f"DETENIDO EN ANÁLISIS {fase}", arbol=arbol,
            errores_lexicos=errores_lexicos, errores_sintacticos=errores_sintacticos,
        )
        return 1

    tabla, errores_semanticos = analizar_semantico(arbol)
    if not errores_semanticos:
        generador = salidas.GeneradorIntermedio(tabla)
        intermedio = generador.generar(arbol)
        ensamblador = salidas.generar_ensamblador(intermedio, generador.etiquetas, tabla=tabla)
    escribir_imagen_arbol(nombre, arbol)

    print(f"\n{CIAN}ÁRBOL SINTÁCTICO{RESET}")
    print(salidas.arbol_dibujado_texto(arbol) or f"{GRIS}(ÁRBOL VACÍO){RESET}")
    print(f"\n{CIAN}TABLA DE SÍMBOLOS{RESET}")
    print(salidas.tabla_simbolos_texto(tabla) or f"{GRIS}(SIN SÍMBOLOS){RESET}")

    escribir_archivo(CONFIG["ARCHIVO_SIMBOLOS"], salidas.contenido_simbolos(nombre, tabla))

    if errores_semanticos:
        mostrar_errores("ERRORES SEMÁNTICOS", errores_semanticos)
        print(
            f"{ROJO}COMPILACIÓN CON {len(errores_semanticos)} "
            f"ERROR(ES) SEMÁNTICO(S).{RESET}"
        )
        estado = "DETENIDO EN ANÁLISIS SEMÁNTICO"
    else:
        escribir_archivo(CONFIG["ARCHIVO_ANALISIS"], salidas.generar_codigo(arbol))
        escribir_archivo(CONFIG["ARCHIVO_INTERMEDIO"], intermedio)
        escribir_archivo(CONFIG["ARCHIVO_ENSAMBLADOR"], ensamblador)
        estado = "COMPILACIÓN CORRECTA"

    escribir_reporte(
        nombre, tokens, estado, arbol=arbol, tabla=tabla, errores_semanticos=errores_semanticos,
    )

    if errores_semanticos:
        return 1
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
