# Matriz de transición léxica de CE

Abre `MATRIZ_TRANSICION.csv` en Excel. Si todo aparece en una columna, usa **Datos → Desde texto/CSV**, selecciona **UTF-8** y el delimitador **punto y coma (`;`)**. Guarda el mismo formato si editas la tabla; `CE.py` la carga desde su propia carpeta al iniciar.

Cada fila es un estado; cada columna después de `RESULTADO` es una clase de entrada. Todas las celdas de transición tienen un estado destino. `q0` es el estado inicial de cada lexema. `q_error` es el estado de rechazo: sus transiciones regresan a sí mismo, pero el analizador detiene el recorrido antes de entrar en él. Se devuelve el último resultado encontrado sin consumir el carácter que provocó el rechazo.

`RESULTADO` indica el tipo de token, un separador (`ESPACIO` o `SALTO`) o un diagnóstico (`ERROR_*`, definido en `DEFINICIONES.TXT`). Las celdas de `RESULTADO` de `q0` y `q_error` están vacías porque esos estados no emiten nada.

| Reconocedor | Filas |
| --- | --- |
| Identificadores y las 18 reservadas | `id_general`, `pr_*` |
| Enteros, decimales y errores numéricos | `num_*`, `punto_solo` |
| Literales de carácter y de cadena | `car_*`, `cad_*` |
| Operadores aritméticos, de asignación, comparación, negación y lógicos | `op_*` |
| Delimitadores | `del_*` |
| Espacios, tabulaciones y saltos de línea | `blanco`, `salto_*` |
| Símbolos no reconocidos y estado de rechazo | `simbolo_invalido`, `q_error` |

- Las columnas `a` a `z` permiten seguir los prefijos de las reservadas. `OTRA_LETRA` agrupa las mayúsculas ASCII y `áéíóúüñÁÉÍÓÚÜÑ`. `DIGITO` agrupa `0` a `9`; `OTRO` contiene cualquier carácter que no tenga otra columna.
- `si` termina en `pr_si` y produce `SI`; una `n` permite seguir hacia `sino`, pero un dígito lleva a `id_general`, por lo que `si2` se reconoce como un único `ID`.
- La primera comilla doble lleva a `cad_abierta`; la segunda, a `cad_cerrada` (`LITERAL_CADENA`). CR y LF llevan de `cad_abierta` a `q_error`: una cadena sin cierre produce el error 106 y deja el salto para el siguiente recorrido.
