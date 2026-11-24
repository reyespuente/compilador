import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import CE


class PruebasLexico(unittest.TestCase):
    def test_reservadas_e_identificadores(self):
        tokens, errores = CE.tokenizar("si sino si2 mientras1 mostrar Mostrar _ñ")
        self.assertFalse(errores)
        self.assertEqual(
            [(t.tipo, t.lexema) for t in tokens],
            [
                ("SI", "si"), ("SINO", "sino"), ("ID", "si2"),
                ("ID", "mientras1"), ("MOSTRAR", "mostrar"),
                ("ID", "Mostrar"), ("ID", "_ñ"),
            ],
        )

    def test_operadores_y_delimitadores(self):
        operadores = "+ - * / % = == ! != < <= > >= && ||".split()
        tokens, errores = CE.tokenizar(" ".join(operadores) + "(){};,:")
        self.assertFalse(errores)
        self.assertEqual([t.lexema for t in tokens], operadores + list("(){};,:"))
        self.assertEqual([t.tipo for t in tokens[:len(operadores)]], ["OPERADOR"] * len(operadores))
        self.assertEqual(
            [t.tipo for t in tokens[len(operadores):]],
            ["PAR_IZQ", "PAR_DER", "LLAVE_IZQ", "LLAVE_DER", "PUNTO_COMA", "COMA", "DOS_PUNTOS"],
        )

    def test_literales_y_errores(self):
        tokens, errores = CE.tokenizar(
            """0 3.14 'ñ' "hola mundo" "" . 'ab' 12abc & | 12. .5 "sin cerrar"""
        )
        self.assertEqual(
            [(t.tipo, t.lexema) for t in tokens],
            [
                ("NUMERO_ENTERO", "0"), ("NUMERO_DECIMAL", "3.14"),
                ("LITERAL_CARACTER", "'ñ'"), ("LITERAL_CADENA", '"hola mundo"'),
                ("LITERAL_CADENA", '""'),
            ],
        )
        self.assertEqual(
            [(e.codigo, e.lexema) for e in errores],
            [
                (101, "."), (102, "'ab'"), (103, "12abc"),
                (104, "&"), (104, "|"), (105, "12."), (105, ".5"),
                (106, '"sin cerrar'),
            ],
        )

    def test_posiciones_y_saltos(self):
        tokens, errores = CE.tokenizar('"incompleta\r\n\tb\rc\nd')
        self.assertEqual([(e.codigo, e.linea, e.columna) for e in errores], [(106, 1, 1)])
        self.assertEqual(
            [(t.lexema, t.linea, t.columna) for t in tokens],
            [("b", 2, 9), ("c", 3, 1), ("d", 4, 1)],
        )

    def test_matriz_completa_y_rechazo_sin_consumir(self):
        for _, transiciones in CE.MATRIZ_TRANSICION.values():
            self.assertEqual(set(transiciones), CE.CLASES_ENTRADA)
        self.assertEqual(
            CE.MATRIZ_TRANSICION["q_error"],
            ("", dict.fromkeys(CE.CLASES_ENTRADA, "q_error")),
        )

        tokens, errores = CE.tokenizar("si;&&&mostrar")
        self.assertEqual(
            [(t.tipo, t.lexema, t.columna) for t in tokens],
            [("SI", "si", 1), ("PUNTO_COMA", ";", 3),
             ("OPERADOR", "&&", 4), ("MOSTRAR", "mostrar", 7)],
        )
        self.assertEqual([(e.codigo, e.lexema, e.columna) for e in errores], [(104, "&", 6)])

    def test_el_resultado_se_lee_del_csv(self):
        with Path(CE.ARCHIVO_MATRIZ).open(encoding="utf-8-sig", newline="") as archivo:
            filas = list(csv.reader(archivo, delimiter=";"))
        next(fila for fila in filas if fila[0] == "pr_mostrar")[1] = "ID"

        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "matriz.csv"
            with ruta.open("w", encoding="utf-8", newline="") as archivo:
                csv.writer(archivo, delimiter=";").writerows(filas)
            matriz = CE.cargar_matriz(ruta, CE.mensajes)

        with patch.object(CE, "MATRIZ_TRANSICION", matriz):
            self.assertEqual(CE.tokenizar("mostrar"), ([CE.Token("ID", "mostrar", 1, 1)], []))


if __name__ == "__main__":
    unittest.main()
