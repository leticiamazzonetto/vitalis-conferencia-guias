"""
mcp_server/server.py — O MCP da conferência de guias da Clínica Vitalis.

MCP (Model Context Protocol) é a "tomada" padrão que deixa um assistente de IA (Claude,
Claude Code, Claude Desktop e outros) usar o nosso verificador como ferramenta. Este
servidor NÃO tem regra própria: cada ferramenta chama uma função de servico.py, a mesma
que o site chama. Se a regra mudar em motor.py, muda aqui junto.

Ferramentas:
  consultar_regra(convenio, procedimento_codigo)  -> o que o convênio exige e cobre
  verificar_guia(guia)                           -> decisão + motivos + o que fazer
  resumo_lote()                                  -> os números do lote de agosto

Dois transportes do MESMO servidor:
  stdio (padrão): o assistente sobe o processo local.  python mcp_server/server.py
  HTTP:  publicado na VPS atrás do Caddy.               python mcp_server/server.py --http
         (porta interna 8503, caminho /mcp; qualquer assistente conecta sem instalar nada)

Fonte dos dados: dados/regras_convenio.json e dados/guias.csv, lidos direto do disco.
Chave da IA (opcional): variável de ambiente ANTHROPIC_API_KEY. Sem ela, a observação da
recepção vira "requer leitura humana", nunca erro.
"""

import os
import sys
from typing import Any

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from mcp.server.mcpserver import MCPServer  # noqa: E402  (SDK mcp 2.x)

import observacao as obs_mod  # noqa: E402
from servico import consultar_regra as _consultar_regra  # noqa: E402
from servico import verificar_guia as _verificar_guia, duplicatas_de  # noqa: E402
from verificar_lote import processar_lote, resumir  # noqa: E402
sys.path.insert(0, os.path.join(RAIZ, "app"))
from armazenamento import obter_storage  # noqa: E402

CSV = os.path.join(RAIZ, "dados", "guias.csv")
REGRAS = os.path.join(RAIZ, "dados", "regras_convenio.json")

mcp = MCPServer(
    "vitalis-guias",
    instructions=(
        "Conferência de guias de convênio da Clínica Vitalis antes do envio. "
        "Use consultar_regra para saber o que um convênio exige e cobre, verificar_guia para "
        "conferir uma guia como a recepção lançou (aceita data dd/mm/aaaa, vírgula no valor e "
        "campos faltando) e resumo_lote para os números do lote de agosto. "
        "As decisões são OK, CORRIGIR (a recepção resolve no sistema antes do envio) e "
        "NÃO ENVIAR (faturar particular ou cópia a descartar)."
    ),
)

_LOTE_CACHE: dict[str, Any] = {}


def _lote():
    """Lote de agosto (cache) + guias importadas pelo site. IA ligada se houver chave."""
    if "decisoes" not in _LOTE_CACHE:
        decisoes, resumo = processar_lote(CSV, REGRAS, usar_ia=obs_mod.ia_disponivel())
        _LOTE_CACHE["decisoes"] = decisoes
        _LOTE_CACHE["versao"] = resumo.get("versao_regras")
    por_id = {d["id_guia"]: d for d in _LOTE_CACHE["decisoes"]}
    try:
        for imp in obter_storage().listar_importadas():
            por_id[imp["id_guia"]] = imp
    except Exception:  # noqa: BLE001
        pass
    lista = list(por_id.values())
    return lista, resumir(lista, "data de lançamento de cada guia", _LOTE_CACHE["versao"], obs_mod.ia_disponivel())


@mcp.tool()
def consultar_regra(convenio: str, procedimento_codigo: str = "") -> dict:
    """O que um convênio exige e cobre. Informe o nome do convênio (Vitalcard, Saúde Interior
    ou Plano Bem) e, opcionalmente, o código do procedimento para saber se é coberto e o valor
    de referência. Convênio desconhecido devolve ok=false com a lista dos conhecidos."""
    try:
        return _consultar_regra(convenio or "", procedimento_codigo or None)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "erro": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
def verificar_guia(guia: dict) -> dict:
    """Confere UMA guia como a recepção lançou e devolve decisao (OK | CORRIGIR | NÃO ENVIAR),
    motivos, correcoes (o que fazer), alertas, valor_em_risco e valor_reclassificar.
    `guia` é um objeto com os campos do dicionário da prova: id_guia, unidade, data_atendimento,
    paciente, convenio, carteirinha, cid, procedimento_codigo, numero_autorizacao,
    autorizacao_validade, autorizacao_sessoes_limite, sessao_numero_na_autorizacao,
    profissional, profissional_registro, valor, observacao_recepcao, data_lancamento.
    Aceita data dd/mm/aaaa, vírgula no valor e campos faltando; nunca levanta erro.
    Se já existir guia igual no lote de agosto, esta é tratada como cópia (NÃO ENVIAR)."""
    try:
        if not isinstance(guia, dict):
            return {"ok": False, "erro": "guia precisa ser um objeto com os campos da guia"}
        decisoes, _ = _lote()
        ids_dup, nova = duplicatas_de(guia, decisoes)
        d = _verificar_guia(guia, ids_duplicata=ids_dup, usar_ia=obs_mod.ia_disponivel(), guia_nova=nova)
        d["ok"] = True
        return d
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "erro": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
def resumo_lote() -> dict:
    """Os números do conjunto atual (80 guias de agosto + as importadas pelo site): total, OK,
    CORRIGIR, NÃO ENVIAR, valores, problemas por tipo, por unidade e por convênio."""
    try:
        _, resumo = _lote()
        return {"ok": True, "resumo": resumo}   # o resumo tem seu próprio campo "ok" (quantidade)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "erro": f"{type(exc).__name__}: {exc}"}


def main():
    if "--http" in sys.argv:
        from mcp.server.transport_security import TransportSecuritySettings
        hosts = [h for h in os.environ.get("VITALIS_MCP_HOSTS", "127.0.0.1:8503,localhost:8503").split(",") if h]
        mcp.run(
            transport="streamable-http",
            host=os.environ.get("VITALIS_MCP_HOST", "127.0.0.1"),
            port=int(os.environ.get("VITALIS_MCP_PORT", "8503")),
            streamable_http_path="/mcp",
            stateless_http=True,   # cada chamada é independente: simples e robusto atrás do Caddy
            json_response=True,
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=True, allowed_hosts=hosts),
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
