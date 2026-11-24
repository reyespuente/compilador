# Compilador CE

Proyecto de Lenguajes y Autómatas II. CE es un lenguaje inspirado en C con palabras reservadas en español. El programa analiza archivos `.CE` en tres fases: léxica, sintáctica y semántica. Este avance genera reportes y código CE normalizado, no ensamblador ni ejecutables.

El analizador léxico recorre [`MATRIZ_TRANSICION.csv`](MATRIZ_TRANSICION.csv) carácter por carácter, sin expresiones regulares. La matriz incluye identificadores, palabras reservadas, literales de carácter y cadena, operadores, delimitadores y diagnósticos léxicos. Consulta la [guía de la matriz](MATRIZ_TRANSICION.md) para leerla en Excel.

## Instalación y uso

Requiere Python 3.10 o posterior. Pillow se usa para generar la imagen del árbol sintáctico.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r REQUIREMENTS.TXT
python CE.py PRUEBA_CORRECTO.CE
```

En PowerShell, crea el entorno con `py -m venv .venv` y actívalo con `.\.venv\Scripts\Activate.ps1`. Ejecuta `python CE.py` sin argumentos para entrar al modo interactivo.

## Archivos de salida

Cada análisis elimina las salidas anteriores en el **directorio de trabajo** y genera estos archivos según la fase alcanzada:

| Archivo | Contenido |
| --- | --- |
| `REPORTE_ANALISIS.TXT` | Estado del análisis, tokens y diagnósticos. |
| `SYMBOLS.TXT` | Tabla de símbolos y referencias de uso. |
| `ARBOL_SINTACTICO.PNG` | Imagen del árbol sintáctico (requiere Pillow). |
| `ANALISIS_OUTPUT.TXT` | Código CE normalizado, solo si el análisis termina sin errores. |

## Pruebas

```bash
python -m unittest -v test_lexico
```

Para probar el programa completo, pasa cualquiera de los archivos `PRUEBA_*.CE` a `CE.py`. `PRUEBA_CORRECTO.CE` termina con código `0`; `PRUEBA_LEXICO.CE`, `PRUEBA_SINTACTICO.CE` y `PRUEBA_SEMANTICO.CE` terminan con código `1` en la fase indicada por su nombre.
