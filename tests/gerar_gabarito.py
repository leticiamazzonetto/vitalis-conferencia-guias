"""
tests/gerar_gabarito.py — Gera tests/gabarito.csv por uma IMPLEMENTAÇÃO INDEPENDENTE.

Este script NÃO importa motor.py. Ele reescreve as regras do convênio do zero, do jeito
mais simples possível, para servir de segunda opinião. Se o motor e este script
discordarem em alguma guia, um dos dois está errado e o teste acusa.

O gabarito gerado foi revisado à mão pela candidata (coluna `revisado`), guia a guia,
contra a tabela de erros do plano. Rode uma vez e commite o CSV:

    python tests/gerar_gabarito.py
"""

import csv
import json
import os
from datetime import date, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(BASE, "dados", "guias.csv")
REGRAS = os.path.join(BASE, "dados", "regras_convenio.json")
SAIDA = os.path.join(BASE, "tests", "gabarito.csv")

# O que a IA deve enxergar nas 5 observações que mudam o quadro (lidas por uma pessoa).
SINAIS_HUMANOS = {
    "G-2608-0030": {"autorizacao_nova": True, "validade_nova": date(2026, 9, 30)},
    "G-2608-0041": {"protocolo_verbal": "771203"},
    "G-2608-0034": {"remarcada_de": date(2026, 8, 12)},
    "G-2608-0039": {"faturar_particular": True},
    "G-2608-0069": {"codigo_errado": True},
}
TRIVIAIS = {"trouxe exame novo, anexado ao prontuário.", "pediu recibo para reembolso do plano.",
            "paciente chegou 10 min atrasado.", "confirmado pelo whatsapp na véspera."}


def data(s):
    s = s.strip()
    if "/" in s:
        d, m, a = s.split("/")
        return date(int(a), int(m), int(d))
    return date.fromisoformat(s) if s else None


def dias_uteis(d, n):
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def julgar(g, conv, com_ia):
    """Devolve (estado, motivo_principal) para uma guia, com ou sem IA."""
    sinais = SINAIS_HUMANOS.get(g["id_guia"], {}) if com_ia else {}
    nao_enviar, corrigir = [], []
    da = data(g["data_atendimento"])
    ref = data(g["data_lancamento"])  # conferência simulada na data de lançamento (Expert, 21/09)
    val = data(g["autorizacao_validade"])

    # campos obrigatórios
    for campo in conv["campos_obrigatorios"]:
        if not g[campo].strip():
            if campo == "numero_autorizacao" and sinais.get("protocolo_verbal") and conv["nome"] == "Saúde Interior":
                corrigir.append("autorização verbal a regularizar")
            else:
                corrigir.append("campo obrigatório faltando")
    # vencida
    if da and val and val < da:
        if sinais.get("autorizacao_nova") and sinais["validade_nova"] >= da:
            corrigir.append("autorização nova a lançar")
        else:
            corrigir.append("autorização vencida")
    # sessão
    if int(g["sessao_numero_na_autorizacao"]) > conv["limite_sessoes_por_autorizacao"]:
        corrigir.append("sessão acima do limite")
    # cobertura (independente do sinal) / código errado (sinal da IA acrescenta)
    if g["procedimento_codigo"] not in conv["procedimentos_cobertos"]:
        nao_enviar.append("procedimento não coberto")
    if sinais.get("codigo_errado"):
        corrigir.append("código do procedimento errado")
    if sinais.get("faturar_particular"):
        nao_enviar.append("paciente optou por particular")
    # prazo de envio (até a data da conferência)
    if da and (ref - da).days > conv["prazo_envio_dias"]:   # o último dia ainda vale
        corrigir.append("prazo de envio perdido")
    # observação sem IA
    obs = g["observacao_recepcao"].strip().lower()
    if not com_ia and obs and obs not in TRIVIAIS:
        corrigir.append("observação da recepção requer leitura")
    return nao_enviar, corrigir


def main():
    regras = json.load(open(REGRAS, encoding="utf-8"))
    convs = {c["nome"]: c for c in regras["convenios"]}
    guias = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))

    # duplicatas: mesma carteirinha + autorização + data (normalizada) + procedimento
    grupos = {}
    for g in guias:
        k = (g["carteirinha"], g["numero_autorizacao"], data(g["data_atendimento"]), g["procedimento_codigo"])
        grupos.setdefault(k, []).append(g["id_guia"])
    copias = {}
    for ids in grupos.values():
        if len(ids) > 1:
            ids_ord = sorted(ids)
            for c in ids_ord[1:]:
                copias[c] = ids_ord[0]

    linhas = []
    for g in guias:
        conv = convs[g["convenio"]]
        prazo_restante = conv["prazo_envio_dias"] - (data(g["data_lancamento"]) - data(g["data_atendimento"])).days
        for com_ia in (False, True):
            ne, co = julgar(g, conv, com_ia)
            if g["id_guia"] in copias:
                ne.append("cópia de outra guia")
            estado = "NÃO ENVIAR" if ne else ("CORRIGIR" if co else "OK")
            motivo = (ne + co)[0] if (ne + co) else ""
            linhas.append({"id_guia": g["id_guia"], "com_ia": "sim" if com_ia else "não",
                           "estado": estado, "motivo_principal": motivo,
                           "urgente": "sim" if 0 <= prazo_restante <= 7 else "",
                           "revisado": ""})

    with open(SAIDA, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    print(f"gabarito gerado: {SAIDA} ({len(linhas)} linhas)")


if __name__ == "__main__":
    main()
