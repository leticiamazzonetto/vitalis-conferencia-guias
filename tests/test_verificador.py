"""
tests/test_verificador.py — Testes do núcleo (normalizador + motor), só unittest da stdlib.

Um teste por regra e por tipo de sinal da IA, mais a regressão do lote das 80 guias.
A prova de CORREÇÃO do lote (conferência manual guia a guia) está em test_gabarito.py.
Rode com:  python -m unittest discover -s tests -v
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from normalizador import normalizar_data, normalizar_valor, normalizar_guia  # noqa: E402
from motor import verificar, OK, CORRIGIR, NAO_ENVIAR  # noqa: E402
from verificar_lote import processar_lote  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
REGRAS_PATH = os.path.join(BASE, "..", "dados", "regras_convenio.json")
CSV_PATH = os.path.join(BASE, "..", "dados", "guias.csv")

with open(REGRAS_PATH, encoding="utf-8") as f:
    REGRAS = json.load(f)


def guia_base(**kw):
    """Guia Vitalcard válida como esqueleto; os testes sobrescrevem o campo que interessa."""
    base = {
        "id_guia": "G-TESTE", "unidade": "Sul", "data_atendimento": "2026-08-20",
        "paciente": "P-1000", "convenio": "Vitalcard", "carteirinha": "123456789",
        "cid": "M79.7", "procedimento_codigo": "50000470",
        "procedimento_descricao": "Sessão de fisioterapia musculoesquelética",
        "numero_autorizacao": "AUT000001", "autorizacao_validade": "2026-08-30",
        "autorizacao_sessoes_limite": "10", "sessao_numero_na_autorizacao": "3",
        "profissional": "Fulano", "profissional_registro": "CREFITO-3 000000-F",
        "valor": "62.00", "observacao_recepcao": "", "data_lancamento": "2026-08-22",
    }
    base.update(kw)
    return normalizar_guia(base)


def verificar_base(**kw):
    return verificar(guia_base(**kw), REGRAS, data_ref="2026-09-01")


# --------------------------------------------------------------------------- #
# NORMALIZADOR
# --------------------------------------------------------------------------- #
class TestNormalizador(unittest.TestCase):

    def test_data_br_para_iso(self):
        iso, convertida, erro = normalizar_data("03/08/2026")
        self.assertEqual(iso, "2026-08-03")
        self.assertTrue(convertida)
        self.assertIsNone(erro)

    def test_data_iso_permanece(self):
        iso, convertida, erro = normalizar_data("2026-08-03")
        self.assertEqual(iso, "2026-08-03")
        self.assertFalse(convertida)

    def test_data_vazia(self):
        self.assertEqual(normalizar_data(""), ("", False, None))

    def test_data_invalida_nao_quebra(self):
        iso, convertida, erro = normalizar_data("32/13/2026")
        self.assertIsNotNone(erro)

    def test_valor_com_virgula(self):
        self.assertEqual(normalizar_valor("62,00"), (62.0, True, None))

    def test_valor_com_ponto(self):
        self.assertEqual(normalizar_valor("70.00"), (70.0, False, None))

    def test_valor_com_milhar_br(self):
        self.assertEqual(normalizar_valor("1.234,56"), (1234.56, True, None))

    def test_valor_invalido_nao_quebra(self):
        numero, _, erro = normalizar_valor("abc")
        self.assertIsNone(numero)
        self.assertIsNotNone(erro)

    def test_trim_de_campos(self):
        g = normalizar_guia({"carteirinha": "  123  ", "convenio": " Vitalcard "})
        self.assertEqual(g["carteirinha"], "123")
        self.assertEqual(g["convenio"], "Vitalcard")

    def test_chave_duplicata_ignora_formato_de_data(self):
        g1 = normalizar_guia({"carteirinha": "9", "numero_autorizacao": "A",
                              "data_atendimento": "26/08/2026", "procedimento_codigo": "P"})
        g2 = normalizar_guia({"carteirinha": "9", "numero_autorizacao": "A",
                              "data_atendimento": "2026-08-26", "procedimento_codigo": "P"})
        self.assertEqual(g1["_chave_dup"], g2["_chave_dup"])


# --------------------------------------------------------------------------- #
# MOTOR: uma regra por teste
# --------------------------------------------------------------------------- #
class TestMotor(unittest.TestCase):

    def test_guia_ok(self):
        d = verificar_base()
        self.assertEqual(d["decisao"], OK)
        self.assertEqual(d["motivos"], [])
        self.assertEqual(d["valor_em_risco"], 0.0)

    def test_autorizacao_vencida(self):
        d = verificar_base(autorizacao_validade="2026-08-10", data_atendimento="2026-08-20")
        self.assertEqual(d["decisao"], CORRIGIR)
        self.assertIn("autorização vencida", d["tipos"])
        self.assertEqual(d["valor_em_risco"], 62.0)

    def test_campo_obrigatorio_cid_exigido_no_vitalcard(self):
        d = verificar_base(cid="")
        self.assertEqual(d["decisao"], CORRIGIR)
        self.assertIn("campo obrigatório faltando", d["tipos"])

    def test_cid_nao_exigido_no_saude_interior(self):
        d = verificar(guia_base(convenio="Saúde Interior", cid="",
                                sessao_numero_na_autorizacao="3",
                                autorizacao_sessoes_limite="20",
                                procedimento_codigo="50000470"),
                      REGRAS, data_ref="2026-09-01")
        self.assertEqual(d["decisao"], OK, d["motivos"])

    def test_sessao_acima_do_limite_usa_json(self):
        d = verificar_base(sessao_numero_na_autorizacao="15")
        self.assertIn("sessão acima do limite", d["tipos"])
        self.assertEqual(d["decisao"], CORRIGIR)

    def test_limite_do_csv_e_ignorado_gera_alerta(self):
        d = verificar_base(sessao_numero_na_autorizacao="12", autorizacao_sessoes_limite="99")
        self.assertIn("sessão acima do limite", d["tipos"])
        self.assertTrue(any("diverge" in a for a in d["alertas"]))

    def test_procedimento_nao_coberto_nao_envia(self):
        d = verificar(guia_base(convenio="Plano Bem", procedimento_codigo="20103301",
                                autorizacao_sessoes_limite="12"),
                      REGRAS, data_ref="2026-09-01")
        self.assertIn("procedimento não coberto", d["tipos"])
        self.assertEqual(d["decisao"], NAO_ENVIAR)
        self.assertEqual(d["valor_em_risco"], 0.0)
        self.assertEqual(d["valor_reclassificar"], 62.0)

    def test_prazo_de_envio_perdido_conta_ate_a_data_de_referencia(self):
        # Atendimento 01/08, conferência 01/09: 31 dias > 30 do Vitalcard. A data de
        # lançamento NÃO entra: o prazo é para a guia CHEGAR ao convênio.
        d = verificar_base(data_atendimento="2026-08-01", data_lancamento="2026-08-02",
                           autorizacao_validade="2026-08-30")
        self.assertIn("prazo de envio perdido", d["tipos"])
        self.assertEqual(d["dias_para_prazo"], -1)

    def test_prazo_urgente_gera_alerta_mesmo_em_guia_ok(self):
        # Atendimento 05/08, conferência 01/09: restam 3 dias dos 30. OK, mas urgente.
        d = verificar_base(data_atendimento="2026-08-05", autorizacao_validade="2026-08-30")
        self.assertEqual(d["decisao"], OK)
        self.assertTrue(d["urgente"])
        self.assertEqual(d["dias_para_prazo"], 3)
        self.assertTrue(any("URGENTE" in a for a in d["alertas"]))

    def test_ultimo_dia_do_prazo_ainda_vale_e_e_urgente(self):
        # Atendimento 02/08, conferência 01/09: exatamente 30 dias. Válido, mas urgente (0 dias).
        d = verificar_base(data_atendimento="2026-08-02", autorizacao_validade="2026-08-30")
        self.assertEqual(d["decisao"], OK)
        self.assertEqual(d["dias_para_prazo"], 0)
        self.assertTrue(d["urgente"])

    def test_procedimento_vazio_e_campo_obrigatorio(self):
        d = verificar_base(procedimento_codigo="")
        self.assertEqual(d["decisao"], CORRIGIR)
        self.assertIn("campo obrigatório faltando", d["tipos"])

    def test_procedimento_fora_da_tabela_e_corrigir_nao_recusar(self):
        d = verificar_base(procedimento_codigo="5000047")   # dígito a menos: erro de digitação
        self.assertEqual(d["decisao"], CORRIGIR)
        self.assertIn("código do procedimento fora da tabela", d["tipos"])

    def test_observacao_trivial_sem_ponto_final_continua_trivial(self):
        d = verificar_base(observacao_recepcao="Pediu recibo para reembolso do plano")
        self.assertEqual(d["decisao"], OK)

    def test_duplicata_com_ids_sem_numero_tem_uma_original(self):
        a = verificar(guia_base(id_guia="G-NOVA-ABC"), REGRAS, data_ref="2026-09-01", ids_duplicata=["G-NOVA-XYZ"])
        b = verificar(guia_base(id_guia="G-NOVA-XYZ"), REGRAS, data_ref="2026-09-01", ids_duplicata=["G-NOVA-ABC"])
        self.assertEqual({a["decisao"], b["decisao"]}, {OK, NAO_ENVIAR})

    def test_convenio_nao_string_nao_quebra(self):
        d = verificar_base(convenio=7)
        self.assertEqual(d["decisao"], CORRIGIR)
        self.assertIn("convênio desconhecido", d["tipos"])

    def test_formato_br_e_virgula_nao_reprovam(self):
        d = verificar_base(data_atendimento="20/08/2026", valor="62,00")
        self.assertEqual(d["decisao"], OK, d["motivos"])

    def test_valor_divergente_da_referencia_gera_alerta(self):
        d = verificar_base(valor="99,00")
        self.assertEqual(d["decisao"], OK)
        self.assertTrue(any("diverge da referência" in a for a in d["alertas"]))

    def test_duplicata_copia_nao_envia_e_original_ganha_alerta(self):
        copia = verificar(guia_base(id_guia="G-2608-0058"), REGRAS, data_ref="2026-09-01",
                          ids_duplicata=["G-2608-0057"])
        self.assertEqual(copia["decisao"], NAO_ENVIAR)
        self.assertIn("cópia de outra guia", copia["tipos"])
        self.assertTrue(any("0057" in m for m in copia["motivos"]))
        self.assertEqual(copia["valor_reclassificar"], 0.0)  # o valor conta 1x por par
        original = verificar(guia_base(id_guia="G-2608-0057"), REGRAS, data_ref="2026-09-01",
                             ids_duplicata=["G-2608-0058"])
        self.assertEqual(original["decisao"], OK)
        self.assertTrue(any("cópia" in a for a in original["alertas"]))

    def test_observacao_nao_trivial_sem_ia_pede_leitura(self):
        d = verificar_base(observacao_recepcao="Paciente pediu para faturar como particular.")
        self.assertIn("observação da recepção requer leitura", d["tipos"])
        self.assertEqual(d["decisao"], CORRIGIR)

    def test_observacao_trivial_sem_ia_nao_reprova(self):
        d = verificar_base(observacao_recepcao="Pediu recibo para reembolso do plano.")
        self.assertEqual(d["decisao"], OK)

    def test_convenio_desconhecido_erro_tratado(self):
        d = verificar_base(convenio="Convênio Fantasma")
        self.assertEqual(d["decisao"], CORRIGIR)
        self.assertIn("convênio desconhecido", d["tipos"])

    def test_data_lixo_nao_quebra(self):
        d = verificar_base(data_atendimento="quando der")
        self.assertEqual(d["decisao"], CORRIGIR)
        self.assertIn("dado inválido", d["tipos"])

    def test_todos_os_motivos_reportados(self):
        d = verificar_base(autorizacao_validade="2026-08-10", data_atendimento="2026-08-20",
                           sessao_numero_na_autorizacao="15", profissional_registro="")
        self.assertGreaterEqual(len(d["motivos"]), 3)


# --------------------------------------------------------------------------- #
# MOTOR + SINAIS DA IA: a IA marca caixinhas, o motor decide
# --------------------------------------------------------------------------- #
class TestMotorComSinais(unittest.TestCase):

    def test_sinal_particular_vira_nao_enviar(self):
        d = verificar(guia_base(observacao_recepcao="quer particular"), REGRAS,
                      data_ref="2026-09-01", sinais={"faturar_particular": True})
        self.assertEqual(d["decisao"], NAO_ENVIAR)
        self.assertIn("paciente optou por particular", d["tipos"])

    def test_sinal_autorizacao_nova_rebaixa_vencida_para_lancar_numero(self):
        d = verificar(guia_base(autorizacao_validade="2026-08-17", data_atendimento="2026-08-21",
                                observacao_recepcao="autorização nova, validade 30/09"),
                      REGRAS, data_ref="2026-09-01",
                      sinais={"autorizacao_nova": True, "validade_nova": "2026-09-30"})
        self.assertEqual(d["decisao"], CORRIGIR)
        self.assertIn("autorização nova a lançar", d["tipos"])
        self.assertNotIn("autorização vencida", d["tipos"])

    def test_sinal_protocolo_verbal_no_saude_interior_tem_prazo(self):
        g = guia_base(convenio="Saúde Interior", numero_autorizacao="", cid="",
                      autorizacao_sessoes_limite="20", data_atendimento="2026-08-20",
                      observacao_recepcao="autorizado por telefone, protocolo 771203")
        d = verificar(g, REGRAS, data_ref="2026-08-25", sinais={"protocolo_verbal": "771203"})
        self.assertEqual(d["decisao"], CORRIGIR)
        self.assertIn("autorização verbal a regularizar", d["tipos"])
        self.assertTrue(any("2026-08-27" in m for m in d["motivos"]))  # 5 dias úteis após 20/08

    def test_sinal_protocolo_verbal_na_vitalcard_nao_vale(self):
        d = verificar(guia_base(numero_autorizacao="", observacao_recepcao="verbal 123"),
                      REGRAS, data_ref="2026-09-01", sinais={"protocolo_verbal": "123"})
        self.assertIn("campo obrigatório faltando", d["tipos"])

    def test_sinal_codigo_errado(self):
        d = verificar(guia_base(observacao_recepcao="foi drenagem"), REGRAS, data_ref="2026-09-01",
                      sinais={"codigo_errado": True, "procedimento_real": "drenagem linfática"})
        self.assertEqual(d["decisao"], CORRIGIR)
        self.assertIn("código do procedimento errado", d["tipos"])

    def test_sinal_codigo_errado_nao_esconde_procedimento_nao_coberto(self):
        d = verificar(guia_base(procedimento_codigo="40201015", observacao_recepcao="foi outra coisa"),
                      REGRAS, data_ref="2026-09-01", sinais={"codigo_errado": True})
        self.assertEqual(d["decisao"], NAO_ENVIAR)
        self.assertIn("procedimento não coberto", d["tipos"])
        self.assertIn("código do procedimento errado", d["tipos"])

    def test_sinal_verbal_sem_data_de_atendimento_nao_escreve_None(self):
        g = guia_base(convenio="Saúde Interior", numero_autorizacao="", cid="", data_atendimento="",
                      autorizacao_sessoes_limite="20", observacao_recepcao="verbal 1")
        d = verificar(g, REGRAS, data_ref="2026-09-01", sinais={"protocolo_verbal": "1"})
        self.assertFalse(any("None" in m for m in d["motivos"] + d["correcoes"]))

    def test_sinal_remarcada_com_validade_ok_so_alerta(self):
        d = verificar(guia_base(observacao_recepcao="remarcada de 12/08"), REGRAS,
                      data_ref="2026-09-01", sinais={"remarcada_de": "2026-08-12"})
        self.assertEqual(d["decisao"], OK)
        self.assertTrue(any("remarcada" in a for a in d["alertas"]))

    def test_sinal_irrelevante_nao_reprova(self):
        d = verificar(guia_base(observacao_recepcao="chegou 15 min atrasado"), REGRAS,
                      data_ref="2026-09-01", sinais={"irrelevante": True})
        self.assertEqual(d["decisao"], OK)

    def test_sinal_nao_lida_pede_revisao_humana(self):
        d = verificar(guia_base(observacao_recepcao="qualquer coisa"), REGRAS,
                      data_ref="2026-09-01", sinais={"nao_lida": True})
        self.assertEqual(d["decisao"], CORRIGIR)
        self.assertIn("observação não lida pela IA", d["tipos"])


# --------------------------------------------------------------------------- #
# REGRESSÃO do lote real (sem IA). Correção guia a guia: test_gabarito.py.
# --------------------------------------------------------------------------- #
class TestLoteReal(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Sem data_ref: cada guia é conferida na sua data de lançamento (orientação da Expert).
        cls.decisoes, cls.resumo = processar_lote(CSV_PATH, REGRAS_PATH)
        cls.por_id = {d["id_guia"]: d for d in cls.decisoes}

    def test_contagens_gerais(self):
        r = self.resumo
        self.assertEqual(r["total_conferidas"], 80)
        self.assertEqual(r["ok"] + r["corrigir"] + r["nao_enviar"], 80)

    def test_duplicatas_conhecidas(self):
        self.assertEqual(self.por_id["G-2608-0057"]["decisao"], NAO_ENVIAR)
        self.assertEqual(self.por_id["G-2608-0076"]["decisao"], NAO_ENVIAR)
        self.assertTrue(any("0027" in m for m in self.por_id["G-2608-0057"]["motivos"]))
        self.assertTrue(any("cópia" in a for a in self.por_id["G-2608-0027"]["alertas"]))

    def test_nao_cobertos_nao_enviar(self):
        for gid in ("G-2608-0002", "G-2608-0024", "G-2608-0035", "G-2608-0006", "G-2608-0007"):
            self.assertEqual(self.por_id[gid]["decisao"], NAO_ENVIAR, gid)

    def test_lote_conferido_na_data_de_lancamento_nao_tem_urgentes(self):
        # Lançamento é 0 a 3 dias após o atendimento: nenhuma guia perto do prazo de envio.
        self.assertEqual(self.resumo["urgentes"], [])
        self.assertEqual(self.por_id["G-2608-0010"]["data_referencia"], "2026-08-04")
        self.assertEqual(self.por_id["G-2608-0010"]["dias_para_prazo"], 29)

    def test_com_data_ref_forcada_o_prazo_conta_ate_ela(self):
        decisoes, r = processar_lote(CSV_PATH, REGRAS_PATH, data_ref="2026-09-01")
        self.assertEqual(len(r["urgentes"]), 11)

    def test_caso_ok_conhecido(self):
        self.assertEqual(self.por_id["G-2608-0001"]["decisao"], OK)

    def test_texto_livre_0041_sem_ia(self):
        d = self.por_id["G-2608-0041"]
        self.assertEqual(d["decisao"], CORRIGIR)
        self.assertIn("campo obrigatório faltando", d["tipos"])
        self.assertIn("observação da recepção requer leitura", d["tipos"])

    def test_nenhuma_guia_quebrou(self):
        for d in self.decisoes:
            self.assertIn(d["decisao"], (OK, CORRIGIR, NAO_ENVIAR))


if __name__ == "__main__":
    unittest.main(verbosity=2)
