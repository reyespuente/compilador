# Compilador CE

Proyecto de Lenguajes y Autómatas II. CE es un lenguaje inspirado en C con palabras reservadas en español. El compilador analiza archivos `.CE` y, después de validarlos, genera código de tres direcciones y ensamblador GNU para Linux x86-64. GCC ensambla y enlaza la salida para obtener un ejecutable.

El analizador léxico recorre [`MATRIZ_TRANSICION.csv`](MATRIZ_TRANSICION.csv) carácter por carácter, sin expresiones regulares. La matriz incluye identificadores, palabras reservadas, literales de carácter y cadena, operadores, delimitadores y diagnósticos léxicos. Consulta la [guía de la matriz](MATRIZ_TRANSICION.md) para leerla en Excel.

## Cómo seguir el código

Empieza en `procesar_archivo`, en [`CE.py`](CE.py). Ahí se ve el orden de las fases:

1. **Léxico (`tokenizar`)**: el CSV dice a qué estado pasar con cada carácter. El resultado es una lista de tokens con línea y columna.
2. **Sintaxis (`Parser`)**: consume los tokens según la gramática y construye el árbol sintáctico. Por ejemplo, `expresion` reconoce `+` y `-`, mientras que `termino` reconoce `*` y `/`, que tienen mayor precedencia.
3. **Semántica (`AnalizadorSemantico`)**: recorre el árbol para registrar los símbolos y comprobar declaraciones, tipos y constantes.
4. **Código intermedio (`GeneradorIntermedio`)**: recorre el AST validado y emite temporales para los cálculos y etiquetas para controlar el flujo.
5. **Ensamblador (`GeneradorEnsamblador`)**: traduce cada instrucción intermedia a x86-64, reserva espacio en la pila para las variables y los temporales, y usa la biblioteca estándar de C para `mostrar`.

[`salidas.py`](salidas.py) contiene los generadores de código y las funciones que preparan tablas, reportes y el árbol en texto y PNG. No reconoce tokens ni decide si una instrucción es válida.

## Instalación y uso

Requiere Python 3.10 o posterior. Pillow se usa para generar la imagen del árbol sintáctico.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r REQUIREMENTS.TXT
python CE.py PRUEBA_CORRECTO.CE
```

En PowerShell, crea el entorno con `py -m venv .venv` y actívalo con `.\.venv\Scripts\Activate.ps1`. Ejecuta `python CE.py` sin argumentos para entrar al modo interactivo.

## IDE gráfico

En Linux, inicia **CE Studio** con `python IDE.py` o abre un archivo directamente con `python IDE.py PRUEBA_CORRECTO.CE`. Si falta Tkinter, en Debian o Ubuntu puedes instalarlo con `sudo apt install python3-tk`. Para ejecutar también necesitas GCC y Linux x86-64.

- A la izquierda, el editor muestra números de línea y colorea el código usando el léxico de CE.
- **F6** compila el contenido del editor. **F5** compila, ensambla y ejecuta. **Detener** cancela la operación activa; el ejecutable tiene un límite de 10 segundos.
- A la derecha están la fuente compilada, el análisis, los símbolos, el árbol, el CE normalizado, el código intermedio y el ensamblador. Abajo aparece la salida de la terminal. La compilación del IDE usa una carpeta temporal y no sobrescribe los archivos de salida del repositorio.
- Las pestañas **Ayuda** y **Acerca de** incluyen una guía rápida y las cuatro fichas del equipo. Para personalizarlas, edita `EQUIPO` en `IDE.py` y coloca las fotos `foto1.png` a `foto4.png` en `equipo/`.

## Archivos de salida

Cada análisis elimina las salidas anteriores en el **directorio de trabajo** y genera estos archivos según la fase alcanzada:

| Archivo | Contenido |
| --- | --- |
| `REPORTE_ANALISIS.TXT` | Estado del análisis, tokens y diagnósticos. |
| `SYMBOLS.TXT` | Tabla de símbolos y referencias de uso. |
| `ARBOL_SINTACTICO.PNG` | Imagen del árbol sintáctico (requiere Pillow). |
| `ANALISIS_OUTPUT.TXT` | Código CE normalizado, solo si el análisis termina sin errores. |
| `CODIGO_INTERMEDIO.TXT` | Código de tres direcciones, solo si el análisis termina sin errores. |
| `CODIGO_ASM.TXT` | Ensamblador GNU en sintaxis Intel, solo si el análisis termina sin errores. |

La tabla de símbolos se construye en el análisis semántico. Antes de mostrarla o guardarla, el generador de ensamblador anota la ubicación real de cada símbolo en la pila (por ejemplo, `[rbp - 8]`). Si hay errores semánticos, la tabla conserva las declaraciones encontradas, pero su ubicación dice `NO ASIGNADA`. `INICIALIZADOR` muestra la expresión escrita en la declaración, no el valor que tenga la variable al ejecutar el programa.

## Código intermedio

Para `entero n = 2 + 3 * 4;`, el generador emite:

```text
    decl entero @n
    %t1 = 3 * 4
    %t2 = 2 + %t1
    init @n, %t2
```

- `@nombre` referencia una variable o constante, `%t1` es un valor temporal y `%L1` es una etiqueta de salto. `decl` y `const` describen los símbolos de ámbito global; `init` se ejecuta donde estaba la declaración original. Una declaración sin inicializador no asigna un valor.
- `si`/`sino` y `mientras` usan `if … goto` y `goto`. `&&` y `||` saltan el segundo operando cuando el primero basta para decidir. `romper` y `continuar` saltan a la salida o a la condición del ciclo más interno.
- `decimal operando` convierte de entero a decimal cuando lo requiere una operación, comparación o asignación. `param` y `call mostrar, N` representan la salida; `return` representa `retornar`. `endfunc` marca el fin de `principal`, sin inventar un valor de retorno.

## Ensamblar y ejecutar

En Linux x86-64 con GCC instalado:

```bash
python CE.py PRUEBA_CORRECTO.CE
gcc -x assembler CODIGO_ASM.TXT -o programa
./programa
```

`-x assembler` permite usar el archivo con extensión `.TXT`. En este ejemplo el ejecutable imprime `Articulos: 3, total: $71.5`.

- `.intel_syntax noprefix` indica que el destino va primero y que los registros se escriben sin `%`. Las `.equ` dan nombre a las posiciones en la pila; `.Lsi_…` y `.Lprobar_ciclo_…` marcan saltos. La sección `.rodata` contiene los textos (`.asciz`) y las constantes decimales (`.double`).
- El ensamblador reutiliza el resultado que ya está en un registro cuando el siguiente paso lo consume. `mostrar` agrupa textos y valores en una llamada a `printf` cuando caben en los registros de argumentos.
- `mostrar` concatena sus argumentos en orden y agrega un salto de línea. Los decimales se imprimen con hasta 15 cifras significativas, sin imponer un número fijo de decimales.
- El ejecutable usa enteros de 64 bits con signo y `double` (IEEE 754). El desbordamiento entero descarta los bits que no caben; la división entera trunca hacia cero y dividir un entero entre cero provoca un error de ejecución. Los `double` no representan exactamente todos los decimales.
- El almacenamiento inicial queda en cero para números, y vacío para caracteres. `retornar` fija el estado de salida del programa; si se llega al final de `principal` sin `retornar`, el ejecutable termina con estado 0.

## Pruebas

Para probar el programa completo, pasa cualquiera de los archivos `PRUEBA_*.CE` a `CE.py`. `PRUEBA_CORRECTO.CE` termina con código `0`; `PRUEBA_LEXICO.CE`, `PRUEBA_SINTACTICO.CE` y `PRUEBA_SEMANTICO.CE` terminan con código `1` en la fase indicada por su nombre.

GitHub Actions verifica los cuatro ejemplos y ensambla y ejecuta el caso válido con GCC.
