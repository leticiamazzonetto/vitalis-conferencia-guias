"""
tests/test_reenvio.py — Reenviar as mesmas 80 guias pelo caminho de "guia nova" tem de dar
exatamente o resultado do lote. Uma guia com id que já está no lote é a própria guia sendo
reconferida, não uma cópia de si mesma (bug encontrado pela Leticia em 22/09).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servico import verificar_guia, duplicatas_de  # noqa: E402
from verificar_lote import processar_lote, carregar_guias  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(RAIZ, "dados", "guias.csv")
REGRAS = os.path.join(RAIZ, "dados", "regras_convenio.json")


class TestReenvio(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.lote, cls.resumo = processar_lote(CSV, REGRAS, usar_ia=False)
        cls.por_id = {d["id_guia"]: d for d in cls.lote}
        # histórico fictício: uma guia de teste igual à G-2608-0041 (como aconteceu no site)
        chave_0041 = cls.por_id["G-2608-0041"]["chave_duplicata"]
        cls.historico = lambda chave, meu_id: (["G-NOVA-TESTE"] if chave == chave_0041 else [])

    def test_reenviar_as_80_reproduz_o_lote(self):
        divergentes = []
        for bruta in carregar_guias(CSV):
            ids, nova = duplicatas_de(bruta, self.lote, self.historico)
            d = verificar_guia(bruta, ids_duplicata=ids, usar_ia=False, guia_nova=nova)
            esperado = self.por_id[bruta["id_guia"]]["decisao"]
            if d["decisao"] != esperado:
                divergentes.append((bruta["id_guia"], esperado, d["decisao"]))
        self.assertEqual(divergentes, [])

    def test_guia_realmente_nova_igual_a_uma_do_lote_e_copia(self):
        g = dict(carregar_guias(CSV)[58])          # G-2608-0059
        g["id_guia"] = "G-NOVA-0001"
        ids, nova = duplicatas_de(g, self.lote)
        self.assertTrue(nova)
        self.assertIn("G-2608-0059", ids)
        self.assertEqual(verificar_guia(g, ids_duplicata=ids, usar_ia=False, guia_nova=nova)["decisao"], "NÃO ENVIAR")


if __name__ == "__main__":
    unittest.main(verbosity=2)
