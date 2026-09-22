"""
tests/test_observacao.py — A camada de IA sem chamar a API.

`chamar` é trocado por um dublê que devolve o JSON que o modelo devolveria. Testa:
normalização dos sinais, cache, resposta suja, falha (vira nao_lida), e o caminho
completo servico.verificar_guia -> sinais -> motor nos 5 casos reais das 80 guias.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import observacao as obs  # noqa: E402
from motor import OK, CORRIGIR, NAO_ENVIAR  # noqa: E402
from servico import verificar_guia, consultar_regra  # noqa: E402

# Dublê: o que esperamos que o modelo responda para cada observação real do CSV.
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
    "paciente chegou 15 min atrasado.":
        'Claro! Aqui está: {"irrelevante": true} espero ter ajudado',
}


def dublê(prompt, texto, ano):
    chave = texto.strip().lower()
    if chave == "quebra":
        raise RuntimeError("rede caiu")
    if chave == "lixo":
        return "isso não é json"
    return RESPOSTAS[chave]


def cache_temp():
    return obs.Cache(os.path.join(tempfile.mkdtemp(), "c.json"))


class TestExtrairSinais(unittest.TestCase):

    def test_texto_vazio_e_irrelevante_sem_chamar(self):
        s = obs.extrair_sinais("", cache=cache_temp(), chamar=dublê)
        self.assertTrue(s["irrelevante"])
        self.assertFalse(s["nao_lida"])

    def test_normaliza_chaves_e_datas(self):
        s = obs.extrair_sinais("Paciente trouxe autorização nova, número ainda não lançado. Validade 30/09.",
                               cache=cache_temp(), chamar=dublê)
        self.assertTrue(s["autorizacao_nova"])
        self.assertEqual(s["validade_nova"], "2026-09-30")
        self.assertFalse(s["faturar_particular"])
        self.assertIn("codigo_errado", s)

    def test_resposta_com_texto_em_volta(self):
        s = obs.extrair_sinais("Paciente chegou 15 min atrasado.", cache=cache_temp(), chamar=dublê)
        self.assertTrue(s["irrelevante"])

    def test_falha_vira_nao_lida(self):
        s = obs.extrair_sinais("quebra", cache=cache_temp(), chamar=dublê)
        self.assertTrue(s["nao_lida"])

    def test_json_invalido_vira_nao_lida(self):
        s = obs.extrair_sinais("lixo", cache=cache_temp(), chamar=dublê)
        self.assertTrue(s["nao_lida"])

    def test_sem_chave_de_api_vira_nao_lida_sem_chamar_rede(self):
        antiga = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            s = obs.extrair_sinais("qualquer observação", cache=cache_temp())
            self.assertTrue(s["nao_lida"])
        finally:
            if antiga:
                os.environ["ANTHROPIC_API_KEY"] = antiga

    def test_cache_evita_segunda_chamada(self):
        chamadas = []

        def contador(prompt, texto, ano):
            chamadas.append(texto)
            return dublê(prompt, texto, ano)
        c = cache_temp()
        obs.extrair_sinais("Paciente pediu para faturar como particular, não quer usar o convênio.", cache=c, chamar=contador)
        obs.extrair_sinais("paciente pediu para faturar como particular, não quer usar o convênio.", cache=c, chamar=contador)
        self.assertEqual(len(chamadas), 1)

    def test_data_fora_do_formato_e_descartada(self):
        s = obs._normalizar_sinais({"autorizacao_nova": True, "validade_nova": "30/09"})
        self.assertIsNone(s["validade_nova"])


class TestServicoComIA(unittest.TestCase):
    """Os 5 casos reais de texto livre, do texto cru até a decisão."""

    def guia(self, **kw):
        base = {"id_guia": "G-T", "convenio": "Vitalcard", "carteirinha": "1", "cid": "M79.7",
                "procedimento_codigo": "50000470", "numero_autorizacao": "AUT1",
                "autorizacao_validade": "2026-08-30", "sessao_numero_na_autorizacao": "3",
                "profissional_registro": "CREFITO-3 1", "valor": "62,00",
                "data_atendimento": "2026-08-20", "data_lancamento": "2026-08-21"}
        base.update(kw)
        return base

    def verificar(self, **kw):
        return verificar_guia(self.guia(**kw), data_ref="2026-09-01", cache=cache_temp(), chamar=dublê)

    def test_0030_autorizacao_nova_vira_lancar_numero(self):
        d = self.verificar(autorizacao_validade="2026-08-17", data_atendimento="2026-08-21",
                           observacao_recepcao="Paciente trouxe autorização nova, número ainda não lançado. Validade 30/09.")
        self.assertEqual(d["decisao"], CORRIGIR)
        self.assertIn("autorização nova a lançar", d["tipos"])

    def test_0041_protocolo_verbal_saude_interior(self):
        d = self.verificar(convenio="Saúde Interior", numero_autorizacao="", cid="",
                           observacao_recepcao="Autorizado por telefone, protocolo 771203, aguardando número.")
        self.assertEqual(d["decisao"], CORRIGIR)
        self.assertIn("autorização verbal a regularizar", d["tipos"])

    def test_0034_remarcada_validade_cobre(self):
        d = self.verificar(data_atendimento="2026-08-24",
                           observacao_recepcao="Sessão remarcada de 12/08 para hoje, autorização era da data original.")
        self.assertEqual(d["decisao"], OK)
        self.assertTrue(any("remarcada" in a for a in d["alertas"]))

    def test_0039_particular_nao_envia(self):
        d = self.verificar(observacao_recepcao="Paciente pediu para faturar como particular, não quer usar o convênio.")
        self.assertEqual(d["decisao"], NAO_ENVIAR)

    def test_0069_codigo_errado(self):
        d = self.verificar(procedimento_codigo="20103301", valor="90.00",
                           observacao_recepcao="Procedimento realizado foi drenagem linfática, lançar o código certo.")
        self.assertEqual(d["decisao"], CORRIGIR)
        self.assertIn("código do procedimento errado", d["tipos"])

    def test_guia_nova_igual_a_uma_existente_e_a_copia(self):
        d = verificar_guia(self.guia(id_guia="G-NOVA-1"), data_ref="2026-09-01",
                           ids_duplicata=["G-2608-0059"], usar_ia=False)
        self.assertEqual(d["decisao"], NAO_ENVIAR)
        self.assertIn("cópia de outra guia", d["tipos"])

    def test_sem_ia_pede_leitura(self):
        d = verificar_guia(self.guia(observacao_recepcao="Paciente pediu para faturar como particular, não quer usar o convênio."),
                           data_ref="2026-09-01", usar_ia=False)
        self.assertIn("observação da recepção requer leitura", d["tipos"])


class TestConsultarRegra(unittest.TestCase):

    def test_regra_com_procedimento(self):
        r = consultar_regra("Plano Bem", "20103301")
        self.assertTrue(r["ok"])
        self.assertFalse(r["procedimento"]["coberto"])
        self.assertIn("particular", r["observacao"].lower())

    def test_convenio_desconhecido_estruturado(self):
        r = consultar_regra("Fantasma")
        self.assertFalse(r["ok"])
        self.assertIn("Vitalcard", r["convenios_conhecidos"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
