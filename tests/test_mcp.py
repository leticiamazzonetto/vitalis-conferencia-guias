"""
tests/test_mcp.py — O MCP de ponta a ponta, como um assistente o usaria.

Sobe o servidor por stdio num subprocesso (o mesmo comando que o README manda instalar),
lista as ferramentas e chama as três: consultar_regra, verificar_guia e resumo_lote.
Sem chave de IA no ambiente: a observação vira "requer leitura", nunca erro.
"""

import asyncio
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.stdio import stdio_client, StdioServerParameters  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVIDOR = os.path.join(RAIZ, "mcp_server", "server.py")


def _conteudo(resultado):
    """Extrai o dict devolvido pela ferramenta (structuredContent ou texto JSON)."""
    if getattr(resultado, "structuredContent", None):
        sc = resultado.structuredContent
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    for bloco in resultado.content:
        if getattr(bloco, "type", "") == "text":
            return json.loads(bloco.text)
    raise AssertionError("resposta sem conteúdo")


async def _sessao(fn):
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # teste sem IA
    params = StdioServerParameters(command=sys.executable, args=[SERVIDOR], env=env, cwd=RAIZ)
    async with stdio_client(params) as (leitura, escrita):
        async with ClientSession(leitura, escrita) as s:
            await s.initialize()
            return await fn(s)


class TestMCP(unittest.TestCase):

    def test_lista_as_tres_ferramentas(self):
        async def fn(s):
            r = await s.list_tools()
            return sorted(t.name for t in r.tools)
        self.assertEqual(asyncio.run(_sessao(fn)), ["consultar_regra", "resumo_lote", "verificar_guia"])

    def test_consultar_regra(self):
        async def fn(s):
            r = await s.call_tool("consultar_regra", {"convenio": "Plano Bem", "procedimento_codigo": "20103301"})
            return _conteudo(r)
        d = asyncio.run(_sessao(fn))
        self.assertTrue(d["ok"])
        self.assertFalse(d["procedimento"]["coberto"])
        self.assertEqual(d["limite_sessoes_por_autorizacao"], 12)

    def test_consultar_regra_convenio_desconhecido_nao_quebra(self):
        async def fn(s):
            return _conteudo(await s.call_tool("consultar_regra", {"convenio": "Fantasma"}))
        d = asyncio.run(_sessao(fn))
        self.assertFalse(d["ok"])
        self.assertIn("Vitalcard", d["convenios_conhecidos"])

    def test_verificar_guia_nova_com_dado_sujo(self):
        guia = {"id_guia": "G-MCP-1", "convenio": "Vitalcard", "carteirinha": "999", "cid": "",
                "procedimento_codigo": "50000470", "numero_autorizacao": "AUT1",
                "autorizacao_validade": "30/09/2026", "sessao_numero_na_autorizacao": "3",
                "profissional_registro": "CREFITO-3 1", "valor": "62,00",
                "data_atendimento": "28/08/2026", "data_lancamento": "29/08/2026"}

        async def fn(s):
            return _conteudo(await s.call_tool("verificar_guia", {"guia": guia}))
        d = asyncio.run(_sessao(fn))
        self.assertTrue(d["ok"])
        self.assertEqual(d["decisao"], "CORRIGIR")
        self.assertIn("campo obrigatório faltando", d["tipos"])   # Vitalcard exige CID
        self.assertTrue(any("vírgula" in n for n in d["normalizacoes"]))

    def test_verificar_guia_copia_do_lote(self):
        copia = {"id_guia": "G-MCP-2", "convenio": "Vitalcard", "carteirinha": "717376382", "cid": "M79.7",
                 "procedimento_codigo": "50000560", "numero_autorizacao": "AUT743137",
                 "autorizacao_validade": "2026-09-02", "sessao_numero_na_autorizacao": "7",
                 "profissional_registro": "CREFITO-3 204411-F", "valor": "70.00",
                 "data_atendimento": "2026-08-27", "data_lancamento": "2026-08-27"}

        async def fn(s):
            return _conteudo(await s.call_tool("verificar_guia", {"guia": copia}))
        d = asyncio.run(_sessao(fn))
        self.assertEqual(d["decisao"], "NÃO ENVIAR")
        self.assertTrue(any("G-2608-0059" in m for m in d["motivos"]))

    def test_verificar_guia_lixo_nao_quebra(self):
        async def fn(s):
            return _conteudo(await s.call_tool("verificar_guia", {"guia": {"valor": "abc", "convenio": ""}}))
        d = asyncio.run(_sessao(fn))
        self.assertTrue(d["ok"])
        self.assertEqual(d["decisao"], "CORRIGIR")

    def test_resumo_lote(self):
        async def fn(s):
            return _conteudo(await s.call_tool("resumo_lote", {}))
        d = asyncio.run(_sessao(fn))
        self.assertTrue(d["ok"])
        r = d["resumo"]
        self.assertEqual(r["total_conferidas"], 80)
        self.assertEqual(r["ok"] + r["corrigir"] + r["nao_enviar"], 80)
        self.assertIn("problemas_por_tipo", r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
