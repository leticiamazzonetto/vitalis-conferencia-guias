"""
gerar_relatorio.py — Gera o "relatório de terça" do Dr. Renato a partir do resultados.json.

Ordem do relatório (a ordem em que o dono precisa ler):
  1. O que morre esta semana (urgentes: a ≤ 7 dias do prazo de envio)
  2. O que a recepção corrige (CORRIGIR, com R$ em risco)
  3. O que precisa de decisão (NÃO ENVIAR: reclassificar ou descartar)
  4. Cortes por unidade e por convênio
  5. Top 3 ações da semana
Uma página, linguagem de dono de clínica, número antes de adjetivo. Só stdlib.

Uso:
    python gerar_relatorio.py --entrada resultados.json --md relatorio-terca.md --html relatorio-terca.html
"""

import argparse
import html
import json
import os

ACAO_POR_TIPO = {
    "autorização vencida":
        "Refazer a autorização das {n} guias com validade vencida antes de qualquer envio.",
    "campo obrigatório faltando":
        "Completar o campo obrigatório que falta em {n} guias (número de autorização, CID ou registro).",
    "sessão acima do limite":
        "Pedir nova autorização ou reavaliação para as {n} guias que passaram do limite de sessões.",
    "procedimento não coberto":
        "Faturar como particular os {n} procedimentos que o convênio não cobre.",
    "observação da recepção requer leitura":
        "Ler as {n} observações da recepção e decidir a exceção.",
    "observação não lida pela IA":
        "Ler à mão as {n} observações que a IA não conseguiu ler.",
    "autorização nova a lançar":
        "Lançar o número da autorização nova em {n} guias (a recepção já tem em mãos).",
    "autorização verbal a regularizar":
        "Lançar o número definitivo das {n} autorizações verbais dentro do prazo do convênio.",
    "código do procedimento errado":
        "Corrigir o código do procedimento em {n} guias antes do envio.",
    "paciente optou por particular":
        "Emitir como particular as {n} guias em que o paciente não quis usar o convênio.",
    "cópia de outra guia":
        "Descartar as {n} guias que são cópia de outra já lançada.",
    "prazo de envio perdido":
        "Enviar hoje as {n} guias com prazo vencido e negociar com o convênio.",
    "convênio desconhecido":
        "Conferir o nome do convênio de {n} guias que não bateram com o cadastro.",
    "dado inválido":
        "Corrigir o dado ilegível de {n} guias e reenviar para conferência.",
    "código do procedimento fora da tabela":
        "Conferir o código do procedimento de {n} guias que não está na tabela.",
}


def plural(n, um, varios):
    return um if n == 1 else varios


def moeda(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def montar_texto(r, periodo=None):
    """periodo: texto do recorte (ex.: 'semana de 03/08 a 09/08'). Sem ele: 'agosto de 2026'."""
    L = []
    L.append("# Relatório semanal · conferência de guias antes do envio")
    L.append("")
    L.append(f"Clínica Vitalis · {periodo or 'agosto de 2026'} · {r['total_conferidas']} guias conferidas")
    L.append("")
    L.append("## O quadro da semana")
    L.append("")
    L.append(f"Foram conferidas {r['total_conferidas']} guias. {r['ok']} estão prontas para envio. "
             f"{r['corrigir']} precisam de correção da recepção e seguram "
             f"{moeda(r['valor_em_risco_total'])} recuperáveis. "
             f"{r['nao_enviar']} não devem ir ao convênio ({moeda(r['valor_reclassificar_total'])} "
             f"a faturar como particular ou descartar).")
    L.append("")
    L.append("## Decisões desta semana")
    L.append("")
    L.append("| Decisão | Guias | Valor |")
    L.append("|---|---:|---:|")
    L.append(f"| Liberar para envio ao convênio (guias OK) | {r['ok']} | {moeda(r.get('valor_ok_total', 0.0))} |")
    L.append(f"| Recepção corrige no sistema antes do envio | {r['corrigir']} | {moeda(r['valor_em_risco_total'])} |")
    L.append(f"| Faturar como particular ou descartar cópia | {r['nao_enviar']} | {moeda(r['valor_reclassificar_total'])} |")
    L.append("")
    L.append("## 1. Prazo de envio vence em 7 dias")
    L.append("")
    urg = r.get("urgentes", [])
    if urg:
        L.append(f"{len(urg)} {plural(len(urg), 'guia está', 'guias estão')} a 7 dias ou menos de perder "
                 f"o prazo de envio ({moeda(r['valor_urgente_total'])}). "
                 f"{plural(len(urg), 'Esta sai', 'Estas saem')} primeiro:")
        L.append("")
        L.append("| Guia | Convênio | Unidade | Dias restantes | Situação | Valor |")
        L.append("|---|---|---|---:|---|---:|")
        for u in urg:
            L.append(f"| {u['id_guia']} | {u['convenio']} | {u['unidade']} | "
                     f"{u['dias_para_prazo']} | {u['decisao']} | {moeda(u['valor'])} |")
    else:
        L.append("Nenhuma guia a menos de 7 dias do prazo de envio: o lote foi conferido na data de "
                 "lançamento, 0 a 3 dias após o atendimento. Este bloco passa a importar na conferência "
                 "semanal, quando a referência é o dia da reunião.")
    L.append("")
    L.append("## 2. Problemas por tipo")
    L.append("")
    L.append("| Tipo de problema | Guias |")
    L.append("|---|---:|")
    for tipo, n in r["problemas_por_tipo"].items():
        L.append(f"| {tipo} | {n} |")
    if not r["problemas_por_tipo"]:
        L.append("| nenhum problema no período | 0 |")
    L.append("")
    if r.get("guias_normalizadas_formato"):
        n = r["guias_normalizadas_formato"]
        L.append(f"{n} {plural(n, 'guia veio', 'guias vieram')} com formato fora do padrão "
                 f"(data brasileira ou vírgula no valor) e {plural(n, 'foi corrigida', 'foram corrigidas')} "
                 f"automaticamente, sem virar pendência.")
        L.append("")
    for titulo, chave in (("3. Por unidade", "por_unidade"), ("4. Por convênio", "por_convenio")):
        L.append(f"## {titulo}")
        L.append("")
        L.append("| | Guias | OK | Corrigir | Não enviar | Recuperável se corrigir | Faturar particular |")
        L.append("|---|---:|---:|---:|---:|---:|---:|")
        for k, d in sorted(r[chave].items(), key=lambda x: -x[1]["valor_em_risco"]):
            L.append(f"| {k} | {d['total']} | {d['ok']} | {d['corrigir']} | {d['nao_enviar']} | "
                     f"{moeda(d['valor_em_risco'])} | {moeda(d['valor_reclassificar'])} |")
        L.append("")
    L.append("## 5. Top 3 ações da semana")
    L.append("")
    for i, (tipo, n) in enumerate(list(r["problemas_por_tipo"].items())[:3], 1):
        L.append(f"{i}. " + ACAO_POR_TIPO.get(tipo, f"Resolver as {{n}} guias de '{tipo}'.").format(n=n))
    L.append("")
    L.append("_Como ler: Recuperável se corrigir = soma das guias CORRIGIR, dinheiro que entra "
             "se a recepção corrigir antes do envio. Faturar particular = soma das NÃO ENVIAR, "
             "não entra pelo convênio; vai como particular ou é cópia a descartar. Conferência feita "
             f"{'em ' if str(r['data_referencia'])[:4].isdigit() else 'na '}{r['data_referencia']} · "
             f"regras {r.get('versao_regras', '')} · "
             f"IA {'ligada' if r.get('com_ia') else 'desligada'}._")
    L.append("")
    return "\n".join(L)


def montar_html(texto_md):
    """Converte o markdown simples do relatório (títulos, parágrafos, tabelas, listas) em HTML."""
    linhas = texto_md.split("\n")
    out, i = [], 0
    while i < len(linhas):
        ln = linhas[i]
        if ln.startswith("# "):
            out.append(f"<h1>{html.escape(ln[2:])}</h1>")
        elif ln.startswith("## "):
            out.append(f"<h2>{html.escape(ln[3:])}</h2>")
        elif ln.startswith("|"):
            rows = []
            while i < len(linhas) and linhas[i].startswith("|"):
                rows.append(linhas[i]); i += 1
            cab = [c.strip() for c in rows[0].strip("|").split("|")]
            out.append("<table><tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in cab) + "</tr>")
            for rw in rows[2:]:
                cels = [c.strip() for c in rw.strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in cels) + "</tr>")
            out.append("</table>")
            continue
        elif ln[:2].rstrip(".").isdigit() and ". " in ln[:4]:
            out.append(f"<p class='acao'>{html.escape(ln)}</p>")
        elif ln.startswith("_") and ln.endswith("_"):
            out.append(f"<footer>{html.escape(ln.strip('_'))}</footer>")
        elif ln.strip():
            out.append(f"<p>{html.escape(ln)}</p>")
        i += 1
    corpo = "\n".join(out)
    return f"""<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório de terça · Clínica Vitalis</title>
<style>
 body{{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;max-width:860px;margin:2rem auto;
      padding:0 1rem;color:#1c2733;line-height:1.5}}
 h1{{font-size:1.5rem;margin-bottom:.2rem}} h2{{font-size:1.15rem;margin-top:1.6rem;color:#0d5a63}}
 table{{border-collapse:collapse;width:100%;margin:.6rem 0;font-size:.95rem}}
 th,td{{border:1px solid #dce3e8;padding:.45rem .6rem;text-align:left}}
 th{{background:#0d5a63;color:#fff}}
 .acao{{margin:.3rem 0 .3rem 1rem}}
 footer{{margin-top:1.6rem;color:#5a6b78;font-size:.85rem}}
</style></head><body>
{corpo}
</body></html>"""


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser()
    p.add_argument("--entrada", default=os.path.join(base, "resultados.json"))
    p.add_argument("--md", default=os.path.join(base, "docs", "relatorio-terca.md"))
    p.add_argument("--html", default=os.path.join(base, "docs", "relatorio-terca.html"))
    args = p.parse_args()
    with open(args.entrada, encoding="utf-8") as f:
        resumo = json.load(f)["resumo"]
    texto = montar_texto(resumo)
    os.makedirs(os.path.dirname(args.md), exist_ok=True)
    with open(args.md, "w", encoding="utf-8") as f:
        f.write(texto + "\n")
    with open(args.html, "w", encoding="utf-8") as f:
        f.write(montar_html(texto))
    print(f"Relatório gerado: {args.md} e {args.html}")


if __name__ == "__main__":
    main()
