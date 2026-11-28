import os
import platform
import selectors
import shutil
import signal
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tempfile import TemporaryDirectory
from threading import Event, Thread
from time import monotonic
from tkinter import filedialog, font, messagebox, ttk

import CE


RAIZ = Path(__file__).resolve().parent
FONDO, PANEL, TEXTO, SUAVE = "#20232a", "#181b20", "#e2e5e9", "#a4adb8"
ACENTO = "#82c7ff"
EJEMPLO = 'entero principal() {\n    mostrar("Hola, CE");\n    retornar 0;\n}\n'
EQUIPO = [
    ("Integrante 1", "2303XXXX", "foto1.png"),
    ("Integrante 2", "2303XXXX", "foto2.png"),
    ("Integrante 3", "2303XXXX", "foto3.png"),
    ("Integrante 4", "2303XXXX", "foto4.png"),
]
REPORTES = [
    ("Análisis", "ARCHIVO_REPORTE"),
    ("Símbolos", "ARCHIVO_SIMBOLOS"),
    ("CE", "ARCHIVO_ANALISIS"),
    ("Intermedio", "ARCHIVO_INTERMEDIO"),
    ("ASM", "ARCHIVO_ENSAMBLADOR"),
]
COLORES_CODIGO = {
    "reservada": "#ff83b5",
    "literal": "#d8df92",
    "numero": "#c7a8ff",
    "operador": "#8fd6e2",
    "error": "#ff8a83",
}


def ejecutar_orden(argumentos, carpeta, cancelar, segundos, limitar=False):
    limite = 256 * 1024
    datos = bytearray()
    aviso = ""
    recortado = False
    hasta = monotonic() + segundos
    with subprocess.Popen(
        argumentos, cwd=carpeta, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
    ) as proceso, selectors.DefaultSelector() as selector:
        selector.register(proceso.stdout, selectors.EVENT_READ)
        while selector.get_map() or proceso.poll() is None:
            if cancelar.is_set():
                aviso = "Operación detenida."
            elif monotonic() >= hasta:
                aviso = f"Se alcanzó el límite de {segundos} segundos."
            if aviso:
                break
            for clave, _ in selector.select(0.1):
                bloque = os.read(clave.fd, 8192)
                if not bloque:
                    selector.unregister(clave.fd)
                    continue
                espacio = limite - len(datos)
                datos.extend(bloque[:espacio])
                if len(bloque) > espacio and limitar:
                    aviso = "Se alcanzó el límite de salida (256 KiB)."
                    break
                recortado |= len(bloque) > espacio
        if aviso:
            try:
                os.killpg(proceso.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        salida = datos.decode("utf-8", errors="replace")
        if recortado:
            salida += "\n[Se recortó la salida de esta orden a 256 KiB.]\n"
        return proceso.wait(), salida, aviso


def compilar_fuente(fuente, nombre, ejecutar, cancelar, registrar):
    with TemporaryDirectory(prefix="ce-ide-") as temporal:
        carpeta = Path(temporal).resolve()
        for clave, salida in CE.CONFIG.items():
            if clave.startswith("ARCHIVO_") and not (carpeta / salida).resolve().is_relative_to(carpeta):
                raise ValueError(f"{clave} debe apuntar dentro de la carpeta de compilación.")
        archivo = carpeta / Path(nombre).name
        archivo.write_text(fuente, encoding="utf-8")
        registrar(f"> Compilar {archivo.name}\n")
        codigo, salida, aviso = ejecutar_orden(
            [sys.executable, str(RAIZ / "CE.py"), str(archivo)], carpeta, cancelar, 30,
        )
        for color in filter(None, CE.COLORES.values()):
            salida = salida.replace(color, "")
        registrar(salida)
        textos = {}
        for _, clave in REPORTES:
            ruta = carpeta / CE.CONFIG[clave]
            if ruta.is_file():
                textos[clave] = ruta.read_text(encoding="utf-8")
        ruta_arbol = carpeta / CE.CONFIG["ARCHIVO_ARBOL"]
        imagen = ruta_arbol.read_bytes() if ruta_arbol.is_file() else b""

        if aviso:
            registrar(aviso + "\n")
            estado = aviso
        elif codigo != 0:
            estado = f"Compilación fallida (código {codigo})."
            registrar(estado + "\n")
        elif ejecutar:
            estado = construir_y_ejecutar(carpeta, cancelar, registrar)
        else:
            estado = "Compilación correcta."
        return textos, imagen, estado


def construir_y_ejecutar(carpeta, cancelar, registrar):
    gcc = shutil.which("gcc")
    asm = carpeta / CE.CONFIG["ARCHIVO_ENSAMBLADOR"]
    programa = carpeta / "programa"
    if cancelar.is_set():
        estado = "Operación detenida."
    elif not (sys.platform.startswith("linux") and platform.machine() in ("x86_64", "amd64")):
        estado = "El ensamblador de CE se ejecuta en Linux x86-64."
    elif not gcc:
        estado = "No se encontró GCC. Instálalo para poder ejecutar."
    elif not asm.is_file():
        estado = "No se generó el archivo de ensamblador."
    else:
        registrar(f"\n> gcc -x assembler {asm.name} -o programa\n")
        codigo, salida, aviso = ejecutar_orden(
            [gcc, "-x", "assembler", str(asm), "-o", str(programa)], carpeta, cancelar, 30,
        )
        registrar(salida)
        if aviso or codigo != 0:
            estado = aviso or f"GCC falló (código {codigo})."
        elif cancelar.is_set():
            estado = "Operación detenida."
        else:
            registrar("\n> ./programa\n")
            codigo, salida, aviso = ejecutar_orden([str(programa)], carpeta, cancelar, 10, limitar=True)
            registrar(salida + ("\n" if salida and not salida.endswith("\n") else ""))
            estado = aviso or f"El programa terminó con código {codigo}."
    registrar(estado + "\n")
    return estado


def panel_desplazable(padre, widget):
    vertical = ttk.Scrollbar(padre, command=widget.yview)
    horizontal = ttk.Scrollbar(padre, orient="horizontal", command=widget.xview)
    widget.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    widget.grid(row=0, column=0, sticky="nsew")
    vertical.grid(row=0, column=1, sticky="ns")
    horizontal.grid(row=1, column=0, sticky="ew")
    padre.rowconfigure(0, weight=1)
    padre.columnconfigure(0, weight=1)
    return vertical


def caja_texto(padre, fuente, **opciones):
    return tk.Text(
        padre, bg=PANEL, fg=TEXTO, insertbackground=TEXTO, selectbackground="#37546d",
        font=fuente, wrap="none", relief="flat", borderwidth=0, padx=8, pady=6, **opciones,
    )


def mostrar_texto(caja, contenido, agregar=False):
    caja.configure(state="normal")
    if not agregar:
        caja.delete("1.0", "end")
    caja.insert("end", contenido)
    caja.see("end" if agregar else "1.0")
    caja.configure(state="disabled")


class EditorCE(ttk.Frame):
    def __init__(self, padre, fuente, al_editar, al_mover):
        super().__init__(padre)
        self.fuente = fuente
        self.al_editar = al_editar
        self.al_mover = al_mover
        self.pendiente = self.coloreado = None
        self.gutter = tk.Canvas(self, bg=FONDO, width=42, highlightthickness=0)
        self.gutter.pack(side="left", fill="y")
        panel = ttk.Frame(self)
        panel.pack(side="left", expand=True, fill="both")
        self.texto = caja_texto(
            panel, fuente, undo=True, width=37, height=18, tabs=fuente.measure(" " * CE.ANCHO_TAB),
        )
        vertical = panel_desplazable(panel, self.texto)
        self.texto.configure(yscrollcommand=lambda *p: self.desplazar(vertical, *p))
        for etiqueta, color in COLORES_CODIGO.items():
            self.texto.tag_configure(etiqueta, foreground=color, underline=etiqueta == "error")
        self.texto.tag_raise("sel")
        self.texto.bind("<<Modified>>", self.cambio)
        self.texto.bind("<Configure>", lambda _: self.agendar_lineas())
        self.texto.bind("<KeyRelease>", lambda _: self.al_mover())
        self.texto.bind("<ButtonRelease-1>", lambda _: self.al_mover())
        self.texto.bind("<Tab>", self.tabular)

    def contenido(self):
        return self.texto.get("1.0", "end-1c")

    def cargar(self, contenido):
        self.texto.delete("1.0", "end")
        self.texto.insert("1.0", contenido)
        self.texto.mark_set("insert", "1.0")
        self.texto.see("1.0")
        self.texto.edit_reset()
        self.texto.edit_modified(False)
        self.refrescar()

    def cambio(self, _):
        if self.texto.edit_modified():
            self.texto.edit_modified(False)
            self.refrescar()
            self.al_editar()

    def refrescar(self):
        self.agendar_lineas()
        if self.coloreado:
            self.after_cancel(self.coloreado)
        self.coloreado = self.after(170, self.colorear)

    def tabular(self, _):
        if self.texto.tag_ranges("sel"):
            self.texto.delete("sel.first", "sel.last")
        self.texto.insert("insert", " " * 4)
        return "break"

    def desplazar(self, barra, *posicion):
        barra.set(*posicion)
        self.agendar_lineas()

    def agendar_lineas(self):
        if self.pendiente is None:
            self.pendiente = self.after_idle(self.dibujar_lineas)

    def dibujar_lineas(self):
        self.pendiente = None
        self.gutter.delete("all")
        total = int(self.texto.index("end-1c").split(".")[0])
        ancho = max(42, self.fuente.measure(str(total)) + 16)
        self.gutter.configure(width=ancho)
        linea = int(self.texto.index("@0,0").split(".")[0])
        while linea <= total and (info := self.texto.dlineinfo(f"{linea}.0")):
            self.gutter.create_text(
                ancho - 7, info[1], text=str(linea),
                anchor="ne", font=self.fuente, fill=SUAVE,
            )
            linea += 1

    def colorear(self):
        self.coloreado = None
        fuente = self.contenido()
        tokens, errores = CE.tokenizar(fuente)
        columnas = []
        for linea in fuente.split("\n"):
            col = 1
            mapa = {}
            for indice, caracter in enumerate(linea):
                mapa[col] = indice
                col = CE.avanzar_columna(col, caracter)
            columnas.append(mapa)

        def colorear_lexema(lexema, etiqueta):
            fila = lexema.linea
            if fila <= len(columnas) and lexema.columna in columnas[fila - 1]:
                inicio = columnas[fila - 1][lexema.columna]
                fin = inicio + len(lexema.lexema)
                self.texto.tag_add(etiqueta, f"{fila}.0 + {inicio} chars", f"{fila}.0 + {fin} chars")

        for etiqueta in COLORES_CODIGO:
            self.texto.tag_remove(etiqueta, "1.0", "end")
        for token in tokens:
            if token.tipo.startswith("LITERAL_"):
                colorear_lexema(token, "literal")
            elif token.tipo.startswith("NUMERO_"):
                colorear_lexema(token, "numero")
            elif token.tipo == "OPERADOR":
                colorear_lexema(token, "operador")
            elif token.tipo != "ID" and token.lexema[0].isalpha():
                colorear_lexema(token, "reservada")
        for error in errores:
            colorear_lexema(error, "error")


class IDE:
    def __init__(self, ventana):
        self.ventana = ventana
        self.ruta = None
        self.original = ""
        self.trabajo = None
        self.cerrar_pendiente = False
        self.eventos = Queue()
        self.fotos = []
        self.imagen = self.vista_imagen = None
        self.reduccion = 1
        self.fuente = font.nametofont("TkFixedFont").copy()
        self.fuente.configure(family="DejaVu Sans Mono", size=11)
        self.estado = tk.StringVar(value="Listo")
        self.posicion = tk.StringVar()
        ventana.geometry("1240x810")
        ventana.minsize(950, 620)
        ventana.configure(bg=FONDO)
        self.estilo()
        self.menu()

        self.paginas = ttk.Notebook(ventana)
        self.paginas.pack(expand=True, fill="both")
        self.pagina = ttk.Frame(self.paginas)
        self.paginas.add(self.pagina, text="Editor")
        self.crear_editor()
        self.crear_ayuda()
        self.crear_acerca()
        self.cargar_documento(None, EJEMPLO)
        ventana.protocol("WM_DELETE_WINDOW", self.cerrar)
        ventana.after(80, self.leer_eventos)

    def estilo(self):
        estilo = ttk.Style(self.ventana)
        estilo.theme_use("clam")
        estilo.configure(".", background=FONDO, foreground=TEXTO, bordercolor=FONDO)
        estilo.configure("TNotebook.Tab", background="#2a2e37", padding=(11, 6))
        estilo.map("TNotebook.Tab", background=[("selected", PANEL)],
                   foreground=[("selected", ACENTO)])
        estilo.configure("TButton", background="#313946", padding=(8, 4))
        estilo.map("TButton", background=[("active", "#405069")],
                   foreground=[("disabled", "#77808c")])
        estilo.configure("Marca.TLabel", foreground=ACENTO, font=("TkDefaultFont", 13, "bold"))
        estilo.configure("Titulo.TLabel", font=("TkDefaultFont", 16, "bold"))
        estilo.configure("Suave.TLabel", foreground=SUAVE)

    def menu(self):
        menu = tk.Menu(self.ventana)
        archivo = tk.Menu(menu, tearoff=False)
        for titulo, atajo, tecla, accion in (
            ("Nuevo", "Ctrl+N", "<Control-n>", self.nuevo),
            ("Abrir…", "Ctrl+O", "<Control-o>", self.abrir),
            ("Guardar", "Ctrl+S", "<Control-s>", self.guardar),
            ("Guardar como…", "", None, lambda: self.guardar(como=True)),
            ("Salir", "", None, self.cerrar),
        ):
            archivo.add_command(label=titulo, accelerator=atajo, command=accion)
            if tecla:
                self.ventana.bind(tecla, lambda _, f=accion: self.atajo(f))
        menu.add_cascade(label="Archivo", menu=archivo)
        self.ventana.config(menu=menu)
        self.ventana.bind("<F6>", lambda _: self.atajo(self.compilar))
        self.ventana.bind("<F5>", lambda _: self.atajo(lambda: self.compilar(True)))

    def atajo(self, accion):
        accion()
        return "break"

    def crear_editor(self):
        barra = ttk.Frame(self.pagina, padding=(10, 6))
        barra.pack(fill="x")
        ttk.Label(barra, text="CE Studio", style="Marca.TLabel").pack(side="left", padx=(0, 14))
        self.botones = []
        for texto, accion in (
            ("Abrir", self.abrir), ("Guardar", self.guardar),
            ("Compilar · F6", self.compilar), ("Compilar y ejecutar · F5", lambda: self.compilar(True)),
        ):
            boton = ttk.Button(barra, text=texto, command=accion)
            boton.pack(side="left", padx=3)
            self.botones.append(boton)
        self.parar = ttk.Button(barra, text="Detener", command=self.detener, state="disabled")
        self.parar.pack(side="left", padx=3)

        piso = ttk.Frame(self.pagina, padding=(10, 4))
        piso.pack(side="bottom", fill="x")
        ttk.Label(piso, textvariable=self.estado).pack(side="left")
        ttk.Label(piso, textvariable=self.posicion, style="Suave.TLabel").pack(side="right")

        vertical = ttk.Panedwindow(self.pagina, orient="vertical")
        vertical.pack(expand=True, fill="both", padx=7, pady=(0, 3))
        horizontal = ttk.Panedwindow(vertical, orient="horizontal")
        vertical.add(horizontal, weight=4)

        izquierda = ttk.Frame(horizontal)
        ttk.Label(izquierda, text="Código fuente  ·  CE", padding=(8, 4)).pack(fill="x")
        self.editor = EditorCE(izquierda, self.fuente, self.actualizar_titulo, self.actualizar_posicion)
        self.editor.pack(expand=True, fill="both")
        horizontal.add(izquierda, weight=5)

        self.resultados = ttk.Notebook(horizontal)
        horizontal.add(self.resultados, weight=6)
        self.vistas = {}
        self.tab_texto("Fuente", "fuente")
        for titulo, clave in REPORTES:
            self.tab_texto(titulo, clave)
            if titulo == "Símbolos":
                self.tab_arbol()

        inferior = ttk.Frame(vertical)
        cabecera = ttk.Frame(inferior, padding=(8, 2))
        cabecera.pack(fill="x")
        ttk.Label(cabecera, text="Terminal").pack(side="left")
        ttk.Button(cabecera, text="Limpiar", command=lambda: mostrar_texto(self.terminal, "")).pack(side="right")
        panel = ttk.Frame(inferior)
        panel.pack(expand=True, fill="both")
        self.terminal = caja_texto(panel, self.fuente, state="disabled", height=8)
        panel_desplazable(panel, self.terminal)
        vertical.add(inferior, weight=1)

    def tab_texto(self, titulo, clave):
        panel = ttk.Frame(self.resultados)
        caja = caja_texto(panel, self.fuente, state="disabled", width=36)
        panel_desplazable(panel, caja)
        self.vistas[clave] = caja
        self.resultados.add(panel, text=titulo)

    def tab_arbol(self):
        panel = ttk.Frame(self.resultados)
        barra = ttk.Frame(panel)
        barra.pack(fill="x")
        ttk.Button(barra, text="Reducir", command=lambda: self.zoom(1)).pack(side="left", padx=4, pady=3)
        ttk.Button(barra, text="Ampliar", command=lambda: self.zoom(-1)).pack(side="left", pady=3)
        marco = ttk.Frame(panel)
        marco.pack(expand=True, fill="both")
        self.arbol = tk.Canvas(marco, bg=PANEL, highlightthickness=0, width=360, height=200)
        panel_desplazable(marco, self.arbol)
        self.resultados.add(panel, text="Árbol")

    def zoom(self, paso):
        self.reduccion = max(1, min(8, self.reduccion + paso))
        if self.imagen:
            self.dibujar_arbol()

    def dibujar_arbol(self, mensaje="No hay un árbol para mostrar."):
        self.arbol.delete("all")
        if self.imagen:
            self.vista_imagen = self.imagen.subsample(self.reduccion) if self.reduccion > 1 else self.imagen
            self.arbol.create_image(0, 0, anchor="nw", image=self.vista_imagen)
        else:
            self.vista_imagen = None
            self.arbol.create_text(14, 15, anchor="nw", fill=SUAVE, text=mensaje)
        self.arbol.configure(scrollregion=self.arbol.bbox("all"))
        self.arbol.xview_moveto(0)
        self.arbol.yview_moveto(0)

    def crear_ayuda(self):
        panel = ttk.Frame(self.paginas, padding=28)
        self.paginas.add(panel, text="Ayuda")
        ttk.Label(panel, text="Cómo usar CE Studio", style="Titulo.TLabel").pack(anchor="w")
        for titulo, descripcion in (
            ("1. Escribe o abre un archivo CE", "Usa Ctrl+O para abrir y Ctrl+S para guardar. El editor muestra las líneas y resalta tokens y errores léxicos."),
            ("2. Compila o ejecuta", "F6 analiza el código y genera las salidas. F5 también ensambla con GCC y ejecuta el programa. Puedes compilar cambios sin guardar."),
            ("3. Revisa el resultado", "A la derecha están la fuente recibida, el reporte, los símbolos, el árbol, el CE normalizado, el código intermedio y el ensamblador."),
            ("4. Mira la terminal", "Abajo salen los diagnósticos y el resultado del ejecutable. Usa Detener si se queda en un ciclo. La ejecución tiene un límite de 10 segundos."),
            ("Requisitos", "Tkinter para el IDE, Pillow para dibujar el PNG y GCC en Linux x86-64 para ejecutar. Las salidas del IDE son temporales."),
        ):
            ttk.Label(panel, text=titulo).pack(anchor="w", pady=(18, 3))
            ttk.Label(panel, text=descripcion, wraplength=800, style="Suave.TLabel").pack(anchor="w")

    def crear_acerca(self):
        panel = ttk.Frame(self.paginas, padding=28)
        self.paginas.add(panel, text="Acerca de")
        ttk.Label(panel, text="CE Studio", style="Titulo.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(panel, text="Lenguajes y Autómatas II · Equipo del compilador CE").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 15),
        )
        for indice, (nombre, control, archivo) in enumerate(EQUIPO):
            tarjeta = ttk.Frame(panel, padding=12, relief="groove")
            tarjeta.grid(row=2 + indice // 2, column=indice % 2, padx=(0, 12), pady=6, sticky="ew")
            foto = tk.Label(tarjeta, bg=PANEL, fg=SUAVE, text="Foto", width=14, height=6)
            try:
                imagen = tk.PhotoImage(master=self.ventana, file=str(RAIZ / "equipo" / archivo))
            except tk.TclError:
                pass
            else:
                escala = max(1, (max(imagen.width(), imagen.height()) + 103) // 104)
                self.fotos.append(imagen.subsample(escala) if escala > 1 else imagen)
                foto.configure(image=self.fotos[-1], text="", width=104, height=104)
            foto.pack(side="left", padx=(0, 14))
            datos = ttk.Frame(tarjeta)
            datos.pack(side="left", fill="both")
            ttk.Label(datos, text=nombre, style="Marca.TLabel").pack(anchor="w")
            ttk.Label(datos, text=f"No. de control: {control}").pack(anchor="w", pady=5)
        for columna in (0, 1):
            panel.columnconfigure(columna, weight=1)

    def actualizar_titulo(self):
        nombre = self.ruta.name if self.ruta else "Sin título"
        marca = " *" if self.editor.contenido() != self.original else ""
        self.ventana.title(f"{nombre}{marca} — CE Studio")
        self.actualizar_posicion()

    def actualizar_posicion(self):
        caja = self.editor.texto
        linea = caja.index("insert").split(".")[0]
        columna = len(caja.get(f"{linea}.0", "insert")) + 1
        self.posicion.set(f"Línea {linea}, columna {columna}   ·   UTF-8")

    def cargar_documento(self, ruta, fuente):
        self.ruta, self.original = ruta, fuente
        self.editor.cargar(fuente)
        self.actualizar_titulo()
        for caja in self.vistas.values():
            mostrar_texto(caja, "Compila el documento para ver esta salida.")
        self.imagen = None
        self.dibujar_arbol()
        self.estado.set("Listo")
        self.paginas.select(self.pagina)
        self.editor.texto.focus_set()

    def confirmar_cambios(self):
        if self.editor.contenido() == self.original:
            return True
        respuesta = messagebox.askyesnocancel("Cambios sin guardar", "¿Quieres guardar los cambios?")
        return respuesta is False or (respuesta is True and self.guardar())

    def nuevo(self):
        if not self.trabajo and self.confirmar_cambios():
            self.cargar_documento(None, "")

    def abrir(self):
        if self.trabajo or not self.confirmar_cambios():
            return
        archivo = filedialog.askopenfilename(
            title="Abrir código CE", filetypes=[("Código CE", "*.CE *.ce"), ("Todos", "*")],
        )
        if archivo:
            self.abrir_ruta(Path(archivo))

    def abrir_ruta(self, ruta):
        try:
            fuente = ruta.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            messagebox.showerror("No se pudo abrir", str(exc))
        else:
            self.cargar_documento(ruta, fuente)

    def guardar(self, como=False):
        ruta = self.ruta
        if como or ruta is None:
            archivo = filedialog.asksaveasfilename(
                title="Guardar código CE", defaultextension=".CE",
                filetypes=[("Código CE", "*.CE *.ce")],
            )
            if not archivo:
                return False
            ruta = Path(archivo)
        fuente = self.editor.contenido()
        try:
            ruta.write_text(fuente, encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            messagebox.showerror("No se pudo guardar", str(exc))
            return False
        self.ruta, self.original = ruta, fuente
        self.actualizar_titulo()
        return True

    def compilar(self, ejecutar=False):
        if self.trabajo:
            return
        nombre = self.ruta.name if self.ruta else "sin_titulo.CE"
        if not nombre.lower().endswith(CE.EXTENSION.lower()):
            nombre += CE.EXTENSION
        fuente = self.editor.contenido()
        self.paginas.select(self.pagina)
        mostrar_texto(self.terminal, "")
        mostrar_texto(self.vistas["fuente"], fuente)
        for clave, caja in self.vistas.items():
            if clave != "fuente":
                mostrar_texto(caja, "Compilando…")
        self.imagen = None
        self.dibujar_arbol("Compilando…")
        self.estado.set("Compilando…")
        cancelar = self.trabajo = Event()
        self.habilitar_acciones(False)

        def trabajar():
            def registrar(texto):
                self.eventos.put(("terminal", texto))

            try:
                resultado = compilar_fuente(fuente, nombre, ejecutar, cancelar, registrar)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                registrar(f"No se pudo completar la operación: {exc}\n")
                resultado = {}, b"", "Operación fallida."
            self.eventos.put(("resultado", resultado))

        Thread(target=trabajar, daemon=True).start()

    def habilitar_acciones(self, habilitar):
        for boton in self.botones:
            boton.configure(state="normal" if habilitar else "disabled")
        self.parar.configure(state="disabled" if habilitar else "normal")

    def detener(self):
        if self.trabajo:
            self.trabajo.set()
            self.parar.configure(state="disabled")
            self.estado.set("Deteniendo…")

    def leer_eventos(self):
        try:
            while True:
                tipo, datos = self.eventos.get_nowait()
                if tipo == "terminal":
                    mostrar_texto(self.terminal, datos, agregar=True)
                else:
                    self.terminar(*datos)
                    if self.cerrar_pendiente:
                        self.ventana.destroy()
                        return
        except Empty:
            pass
        self.ventana.after(80, self.leer_eventos)

    def terminar(self, textos, imagen, estado):
        self.trabajo = None
        self.habilitar_acciones(True)
        self.estado.set(estado)
        for _, clave in REPORTES:
            mostrar_texto(self.vistas[clave], textos.get(clave, "No se generó esta salida."))
        mensaje = "No se generó el PNG. Si hay un árbol en texto, está en Análisis."
        if imagen:
            try:
                self.imagen = tk.PhotoImage(master=self.ventana, data=imagen)
            except tk.TclError:
                mensaje = "No se pudo abrir el PNG. Consulta el árbol en Análisis."
        self.reduccion = 1
        self.dibujar_arbol(mensaje)
        self.resultados.select(1)

    def cerrar(self):
        if self.cerrar_pendiente or not self.confirmar_cambios():
            return
        if self.trabajo:
            self.cerrar_pendiente = True
            self.detener()
        else:
            self.ventana.destroy()


def main():
    try:
        ventana = tk.Tk()
    except tk.TclError as exc:
        print(f"No se pudo abrir CE Studio: {exc}", file=sys.stderr)
        return 1
    aplicacion = IDE(ventana)
    if len(sys.argv) > 1:
        aplicacion.abrir_ruta(Path(sys.argv[1]))
    ventana.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
