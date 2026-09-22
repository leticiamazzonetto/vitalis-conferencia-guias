"""
servico.py — A FONTE ÚNICA de consulta. Duas funções, as mesmas que a prova nomeia.

  consultar_regra(convenio, procedimento_codigo) -> o que o convênio exige e cobre
  verificar_guia(campos, ...)                    -> decisão + motivos + correções

O site (app/app.py) chama estas funções. O MCP (mcp_server/server.py) expõe exatamente
estas funções como ferramentas, sem lógica própria. A Skill chama o MCP. Se a regra
mudar, muda em motor.py e os três mudam juntos.

Fluxo de verificar_guia:  normalizador -> observacao (IA, opcional) -> motor
"""

import json
import os
from datetime import date

from normalizador import normalizar_guia
from motor import verificar
import observacao as obs_mod

BASE = os.path.dirname(os.path.abspath(__file__))
CAMINHO_REGRAS_PADRAO = os.path.join(BASE, "dados", "regras_convenio.json")
# Data de referência da conferência: a data de lançamento da guia (orientação da Expert,
# 21/09/2026: "simula a conferência na data de lançamento") ou, se a guia não tiver, hoje.
DATA_REF_PADRAO = None

_REGRAS_CACHE = {}


def carregar_regras(caminho=None):
    caminho = caminho or CAMINHO_REGRAS_PADRAO
    if caminho not in _REGRAS_CACHE:
        with open(caminho, encoding="utf-8") as f:
            _REGRAS_CACHE[caminho] = json.load(f)
    return _REGRAS_CACHE[caminho]


def consultar_regra(convenio, procedimento_codigo=None, regras=None):
    """
    O que o convênio exige e cobre. Se o procedimento for informado, diz se é coberto
    e o valor de referência. Erro de entrada responde estruturado, nunca exceção.
    """
    if regras is None:
        regras = carregar_regras()
    alvo = (str(convenio) if convenio is not None else "").strip().lower()
    bloco = None
    for c in regras.get("convenios", []):
        if c.get("nome", "").strip().lower() == alvo:
            bloco = c
            break
    if bloco is None:
        return {"ok": False,
                "erro": f"convênio '{convenio}' não está no cadastro",
                "convenios_conhecidos": [c["nome"] for c in regras.get("convenios", [])]}

    saida = {
        "ok": True,
        "convenio": bloco["nome"],
        "campos_obrigatorios": bloco.get("campos_obrigatorios", []),
        "validade_maxima_autorizacao_dias": bloco.get("validade_maxima_autorizacao_dias"),
        "limite_sessoes_por_autorizacao": bloco.get("limite_sessoes_por_autorizacao"),
        "prazo_envio_dias": bloco.get("prazo_envio_dias"),
        "procedimentos_cobertos": bloco.get("procedimentos_cobertos", []),
        "observacao": bloco.get("observacao", ""),
        "versao_regras": regras.get("versao"),
    }
    if procedimento_codigo:
        codigo = str(procedimento_codigo).strip()
        proc = next((p for p in regras.get("procedimentos", []) if p["codigo"] == codigo), None)
        saida["procedimento"] = {
            "codigo": codigo,
            "descricao": proc["descricao"] if proc else None,
            "valor_referencia": proc["valor_referencia"] if proc else None,
            "na_tabela": proc is not None,
            "coberto": codigo in bloco.get("procedimentos_cobertos", []),
        }
    return saida


def verificar_guia(campos, data_ref=None, ids_duplicata=None, usar_ia=True,
                   regras=None, cache=None, chamar=None):
    """
    Confere UMA guia como a recepção lançou. Devolve a Decisao do motor mais o registro
    normalizado (para o site mostrar as normalizações aplicadas).

      campos        : dict com os campos da guia (texto cru; aceita dd/mm e vírgula)
      data_ref      : data ISO da conferência. Padrão: a data de lançamento da guia; sem
                      ela, a data de hoje (guia nova conferida agora).
      ids_duplicata : ids de guias JÁ conferidas com a mesma chave (o chamador consulta o
                      lote/histórico). Se houver, esta guia é a cópia e vira NÃO ENVIAR.
      usar_ia       : False = não lê a observação (modo sem IA; vira "requer leitura")
      cache/chamar  : repassados a observacao.extrair_sinais (testes)
    """
    if regras is None:
        regras = carregar_regras()
    guia = normalizar_guia(campos if isinstance(campos, dict) else {})
    data_ref = data_ref or guia.get("data_lancamento") or date.today().isoformat()

    sinais = None
    if usar_ia and (guia.get("observacao_recepcao") or "").strip():
        ano = int((guia.get("data_atendimento") or data_ref)[:4]) if (guia.get("data_atendimento") or data_ref)[:4].isdigit() else 2026
        kw = {"ano": ano, "cache": cache}
        if chamar is not None:
            kw["chamar"] = chamar
        sinais = obs_mod.extrair_sinais(guia["observacao_recepcao"], **kw)

    decisao = verificar(guia, regras, data_ref=data_ref, ids_duplicata=ids_duplicata,
                        sinais=sinais, guia_nova=True)
    decisao["sinais"] = sinais
    decisao["normalizacoes"] = guia.get("_notas", [])
    decisao["chave_duplicata"] = list(guia.get("_chave_dup", ()))
    decisao["data_referencia"] = data_ref
    decisao["versao_regras"] = regras.get("versao")
    return decisao
