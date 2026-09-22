"""
tests/test_gabarito.py — A prova de CORREÇÃO do lote: o motor contra o gabarito.

tests/gabarito.csv foi gerado por uma implementação independente (gerar_gabarito.py, que
não importa o motor) e revisado à mão. Cada guia tem o estado esperado com e sem IA.
Com IA, os sinais vêm de um dublê que devolve o que uma pessoa leu nas 5 observações
(a chamada real ao modelo é testada à parte, quando há chave).
"""

import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import observacao as obs  # noqa: E402
from verificar_lote import processar_lote  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
GABARITO = os.path.join(BASE, "gabarito.csv")
CSV_PATH = os.path.join(BASE, "..", "dados", "guias.csv")
REGRAS_PATH = os.path.join(BASE, "..", "dados", "regras_convenio.json")

RESPOSTAS = {
    "paciente trouxe autorização nova, número ainda não lançado. validade 30/09.":
        '{"autorizacao_nova": true, "validade_nova": "2026-09-30", "numero_pendente": true}',
    "autorizado por telefone, protocolo 771203, aguardando número.":
        '{"protocolo_verbal": "771203", "numero_pendente": true}',
    "sessão remarcada de 12/08 para hoje, autorização era da data original.":
        '{"remarcada_de": "2026-08-12"}',
    "paciente pediu para faturar como particular, não quer usar o convênio.":
        '{"faturar_particular": true}',
    "procedimento realizado foi drenagem linfática, lançar o código certo.":
        '{"codigo_errado": true, "procedimento_real": "drenagem linfática"}',
}


def dublê(prompt, texto, ano):
    return RESPOSTAS.get(texto.strip().lower(), '{"irrelevante": true}')


class TestGabarito(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(GABARITO, encoding="utf-8") as f:
            linhas = list(csv.DictReader(f))
        cls.esperado = {(l["id_guia"], l["com_ia"]): l for l in linhas}
        sem, _ = processar_lote(CSV_PATH, REGRAS_PATH, usar_ia=False)
        cache = obs.Cache(os.path.join(tempfile.mkdtemp(), "c.json"))
        com, _ = processar_lote(CSV_PATH, REGRAS_PATH, usar_ia=True, chamar=dublê, cache=cache)
        cls.obtido = {("não", d["id_guia"]): d for d in sem}
        cls.obtido.update({("sim", d["id_guia"]): d for d in com})

    def test_gabarito_tem_160_linhas(self):
        self.assertEqual(len(self.esperado), 160)

    def _confere(self, com_ia):
        erros = []
        for (gid, flag), esp in self.esperado.items():
            if flag != com_ia:
                continue
            d = self.obtido[(flag, gid)]
            if d["decisao"] != esp["estado"]:
                erros.append(f"{gid} (IA {flag}): esperado {esp['estado']}, motor {d['decisao']} {d['tipos']}")
            elif esp["motivo_principal"] and esp["motivo_principal"] not in d["tipos"]:
                erros.append(f"{gid} (IA {flag}): motivo esperado '{esp['motivo_principal']}' não está em {d['tipos']}")
            if (esp["urgente"] == "sim") != bool(d.get("urgente")):
                erros.append(f"{gid} (IA {flag}): urgência esperada {esp['urgente']!r}, motor {d.get('urgente')}")
        self.assertEqual(erros, [], "\n" + "\n".join(erros))

    def test_estado_de_cada_guia_sem_ia(self):
        self._confere("não")

    def test_estado_de_cada_guia_com_ia(self):
        self._confere("sim")


if __name__ == "__main__":
    unittest.main(verbosity=2)
