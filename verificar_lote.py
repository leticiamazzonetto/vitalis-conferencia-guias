"""
verificar_lote.py — Porta BATCH do verificador. Roda as guias do CSV pelo núcleo
(normalizador -> [IA nas observações] -> motor) e grava resultados em JSON e CSV.

Uso:
    python verificar_lote.py --csv dados/guias.csv --regras dados/regras_convenio.json \
        --data-ref 2026-09-01 [--com-ia]

Data de referência (o "hoje" da conferência): por orientação da Expert (21/09/2026), o
lote de agosto é conferido NA DATA DE LANÇAMENTO de cada guia ("a guia acabou de ser
lançada e ainda não foi enviada"). O prazo de envio conta da data do atendimento até essa
data. --data-ref força uma data única para todas (útil em testes); sem ela, vale a data de
lançamento de cada guia. Em produção, uma guia nova é conferida na data do dia.

--com-ia liga a leitura das observações pela IA (exige ANTHROPIC_API_KEY). Sem a flag,
as observações não triviais viram CORRIGIR "requer leitura" (modo degradado, sem rede).
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from normalizador import normalizar_guia, chave_valida  # noqa: E402
from motor import verificar, OK, CORRIGIR, NAO_ENVIAR  # noqa: E402
import observacao as obs_mod  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))


def carregar_regras(caminho):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def carregar_guias(caminho):
    """Lê o CSV como lista de dicts. Nunca quebra por linha torta: só ignora vazias."""
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f)
        return [linha for linha in leitor if any((v or "").strip() for v in linha.values())]


def indice_duplicatas(guias_norm):
    """Mapa id -> [ids das outras guias com a MESMA chave]. Só com carteirinha preenchida."""
    grupos = defaultdict(list)
    for g in guias_norm:
        if chave_valida(g["_chave_dup"]):
            grupos[g["_chave_dup"]].append(g.get("id_guia", ""))
    mapa = {}
    for ids in grupos.values():
        if len(ids) > 1:
            for id_atual in ids:
                mapa[id_atual] = [outro for outro in ids if outro != id_atual]
    return mapa


def processar_lote(caminho_csv, caminho_regras, data_ref=None, usar_ia=False,
                   chamar=None, cache=None):
    """Executa o lote inteiro e devolve (decisoes, resumo)."""
    regras = carregar_regras(caminho_regras)
    brutas = carregar_guias(caminho_csv)
    normalizadas = [normalizar_guia(b) for b in brutas]
    mapa_dup = indice_duplicatas(normalizadas)
    cache = cache or (obs_mod.Cache() if usar_ia else None)

    decisoes = []
    for g in normalizadas:
        sinais = None
        obs = (g.get("observacao_recepcao") or "").strip()
        if usar_ia and obs:
            ano = int(g["data_atendimento"][:4]) if (g.get("data_atendimento") or "")[:4].isdigit() else 2026
            kw = {"ano": ano, "cache": cache}
            if chamar is not None:
                kw["chamar"] = chamar
            sinais = obs_mod.extrair_sinais(obs, **kw)
        ids_dup = mapa_dup.get(g.get("id_guia", ""), [])
        ref = data_ref or g.get("data_lancamento") or None
        d = verificar(g, regras, data_ref=ref, ids_duplicata=ids_dup, sinais=sinais)
        d["data_referencia"] = ref
        d["unidade"] = g.get("unidade", "")
        d["paciente"] = g.get("paciente", "")
        d["profissional"] = g.get("profissional", "")
        d["procedimento_codigo"] = g.get("procedimento_codigo", "")
        d["procedimento_descricao"] = g.get("procedimento_descricao", "")
        d["data_atendimento"] = g.get("data_atendimento", "")
        d["data_lancamento"] = g.get("data_lancamento", "")
        d["observacao_recepcao"] = g.get("observacao_recepcao", "")
        d["normalizacoes"] = g.get("_notas", [])
        d["chave_duplicata"] = list(g.get("_chave_dup", ()))
        d["sinais"] = sinais
        decisoes.append(d)

    return decisoes, resumir(decisoes, data_ref or "data de lançamento de cada guia",
                             regras.get("versao"), usar_ia)


def resumir(decisoes, data_ref=None, versao_regras=None, com_ia=False):
    """Consolida os números do lote para o relatório de terça."""
    ok = [d for d in decisoes if d["decisao"] == OK]
    corrigir = [d for d in decisoes if d["decisao"] == CORRIGIR]
    nao_enviar = [d for d in decisoes if d["decisao"] == NAO_ENVIAR]

    por_tipo = defaultdict(int)
    for d in corrigir + nao_enviar:
        for tipo in set(d["tipos"]):
            por_tipo[tipo] += 1

    def novo():
        return {"total": 0, "ok": 0, "corrigir": 0, "nao_enviar": 0,
                "valor_em_risco": 0.0, "valor_reclassificar": 0.0}
    por_unidade, por_convenio = defaultdict(novo), defaultdict(novo)
    for d in decisoes:
        for bloco in (por_unidade[d.get("unidade", "")], por_convenio[d.get("convenio", "")]):
            bloco["total"] += 1
            if d["decisao"] == OK:
                bloco["ok"] += 1
            elif d["decisao"] == CORRIGIR:
                bloco["corrigir"] += 1
            else:
                bloco["nao_enviar"] += 1
            bloco["valor_em_risco"] += d["valor_em_risco"]
            bloco["valor_reclassificar"] += d["valor_reclassificar"]

    urgentes = sorted(
        [{"id_guia": d["id_guia"], "convenio": d["convenio"], "unidade": d.get("unidade", ""),
          "dias_para_prazo": d["dias_para_prazo"], "decisao": d["decisao"],
          "valor": d.get("valor", 0.0)}
         for d in decisoes if d.get("urgente")],
        key=lambda x: (x["dias_para_prazo"], x["id_guia"]),
    )

    return {
        "data_referencia": data_ref,
        "versao_regras": versao_regras,
        "com_ia": com_ia,
        "total_conferidas": len(decisoes),
        "ok": len(ok),
        "corrigir": len(corrigir),
        "nao_enviar": len(nao_enviar),
        "valor_ok_total": round(sum(d.get("valor", 0.0) for d in ok), 2),
        "valor_em_risco_total": round(sum(d["valor_em_risco"] for d in corrigir), 2),
        "valor_reclassificar_total": round(sum(d["valor_reclassificar"] for d in nao_enviar), 2),
        "urgentes": urgentes,
        "valor_urgente_total": round(sum(u["valor"] for u in urgentes), 2),
        "problemas_por_tipo": dict(sorted(por_tipo.items(), key=lambda x: -x[1])),
        "por_unidade": {k: _arredonda(v) for k, v in por_unidade.items()},
        "por_convenio": {k: _arredonda(v) for k, v in por_convenio.items()},
        "guias_normalizadas_formato": sum(1 for d in decisoes if d.get("normalizacoes")),
        "guias_com_alerta": sum(1 for d in decisoes if d.get("alertas")),
    }


def _arredonda(bloco):
    bloco["valor_em_risco"] = round(bloco["valor_em_risco"], 2)
    bloco["valor_reclassificar"] = round(bloco["valor_reclassificar"], 2)
    return bloco


def gravar_json(caminho, decisoes, resumo):
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({"resumo": resumo, "guias": decisoes}, f, ensure_ascii=False, indent=2)


def gravar_csv(caminho, decisoes):
    campos = ["id_guia", "unidade", "convenio", "procedimento_codigo", "data_atendimento",
              "decisao", "urgente", "dias_para_prazo", "tipos", "motivos", "correcoes",
              "alertas", "valor_em_risco", "valor_reclassificar"]
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(campos)
        for d in decisoes:
            w.writerow([d["id_guia"], d.get("unidade", ""), d["convenio"],
                        d.get("procedimento_codigo", ""), d.get("data_atendimento", ""),
                        d["decisao"], "sim" if d.get("urgente") else "",
                        d.get("dias_para_prazo", ""),
                        " | ".join(sorted(set(d["tipos"]))),
                        " | ".join(d["motivos"]), " | ".join(d["correcoes"]),
                        " | ".join(d.get("alertas", [])),
                        f"{d['valor_em_risco']:.2f}", f"{d['valor_reclassificar']:.2f}"])


def main():
    p = argparse.ArgumentParser(description="Confere um lote de guias antes do envio ao convênio.")
    p.add_argument("--csv", default=os.path.join(BASE, "dados", "guias.csv"))
    p.add_argument("--regras", default=os.path.join(BASE, "dados", "regras_convenio.json"))
    p.add_argument("--data-ref", default=None,
                   help="Força uma data de conferência única (ISO). Sem ela: data de lançamento de cada guia.")
    p.add_argument("--com-ia", action="store_true", help="Lê as observações com a IA.")
    p.add_argument("--saida-json", default=os.path.join(BASE, "resultados.json"))
    p.add_argument("--saida-csv", default=os.path.join(BASE, "resultados.csv"))
    args = p.parse_args()

    try:
        if args.data_ref:
            date.fromisoformat(args.data_ref)
    except ValueError:
        print(f"ERRO: --data-ref inválida: {args.data_ref!r} (use aaaa-mm-dd)", file=sys.stderr)
        return 2
    if args.com_ia and not obs_mod.ia_disponivel():
        print("AVISO: --com-ia pedido, mas ANTHROPIC_API_KEY não está definida. "
              "As observações vão sair como 'não lida'.", file=sys.stderr)

    decisoes, r = processar_lote(args.csv, args.regras, data_ref=args.data_ref,
                                 usar_ia=args.com_ia)
    gravar_json(args.saida_json, decisoes, r)
    gravar_csv(args.saida_csv, decisoes)

    print(f"Conferidas: {r['total_conferidas']} | OK: {r['ok']} | CORRIGIR: {r['corrigir']} "
          f"(R$ {r['valor_em_risco_total']:.2f} em risco) | NÃO ENVIAR: {r['nao_enviar']} "
          f"(R$ {r['valor_reclassificar_total']:.2f} a reclassificar)")
    print(f"Urgentes (≤7 dias para o prazo de envio): {len(r['urgentes'])} "
          f"(R$ {r['valor_urgente_total']:.2f})")
    print(f"Data de referência: {r['data_referencia']} | regras {r['versao_regras']} | "
          f"IA: {'ligada' if r['com_ia'] else 'desligada'}")
    print("Problemas por tipo:")
    for tipo, n in r["problemas_por_tipo"].items():
        print(f"  - {tipo}: {n}")
    print(f"Gravado: {args.saida_json} e {args.saida_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
