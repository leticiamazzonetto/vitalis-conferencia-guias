"""
app.py — Site da conferência de guias da Clínica Vitalis (Streamlit).

UMA lógica só: este site chama servico.py (consultar_regra / verificar_guia), as mesmas
duas funções que o MCP expõe e que a Skill usa. Nenhuma regra é reescrita aqui.

Páginas:
  Painel               números do lote, tabela com filtros, detalhe da guia
  Lista de correções   o que cada unidade faz no sistema de gestão, guia por guia
  Conferir guia        formulário, texto colado ou CSV -> decisão + por quê + o que fazer (gravada)
  Relatório semanal    com filtro por semana; cada ação abre a lista de correções filtrada
  Regras dos convênios o que cada convênio exige e cobre
  MCP                  conectar um assistente de IA e usar no dia a dia
  Documentos           Skill, regras, modelo de CSV, instrução da IA, README

Robustez: guia quebrada nunca derruba o site (vira CORRIGIR "dado inválido"); exceção
inesperada vira aviso, não stack trace.

Roda com:  streamlit run app/app.py
"""

import csv
import io
import json
import os
import re
import sys
import traceback
import unicodedata

import pandas as pd
import streamlit as st

BASE_APP = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(BASE_APP)
for p in (RAIZ, BASE_APP):
    if p not in sys.path:
        sys.path.insert(0, p)

from servico import verificar_guia, consultar_regra, carregar_regras, duplicatas_de  # noqa: E402
from normalizador import normalizar_guia  # noqa: E402
from verificar_lote import processar_lote, resumir  # noqa: E402
from datetime import date, timedelta  # noqa: E402
from gerar_relatorio import montar_texto  # noqa: E402
from armazenamento import obter_storage  # noqa: E402
import observacao as obs_mod  # noqa: E402
from motor import OK, CORRIGIR, NAO_ENVIAR  # noqa: E402

CAMINHO_CSV = os.path.join(RAIZ, "dados", "guias.csv")
CAMINHO_REGRAS = os.path.join(RAIZ, "dados", "regras_convenio.json")
DATA_REF = os.environ.get("VITALIS_DATA_REF") or None   # None = data de lançamento (lote) / hoje (guia nova)
IA_LIGADA = obs_mod.ia_disponivel()

st.set_page_config(page_title="Vitalis · Conferência de guias", page_icon="🩺",
                   layout="wide", initial_sidebar_state="expanded")

# ---------------------------------------------------------------------------
# Estilo: cartões, selos de estado e tipografia mais calma
# ---------------------------------------------------------------------------
st.markdown("""
<style>
  .block-container{padding-top:1.6rem;padding-bottom:3rem;max-width:1400px}
  h1{font-size:1.65rem!important;letter-spacing:-.01em;margin-bottom:.2rem!important}
  h2{font-size:1.2rem!important;margin-top:1.4rem!important}
  h3{font-size:1.02rem!important}
  .sub{color:#5C6B66;font-size:.95rem;margin:0 0 1.2rem}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:.4rem 0 1rem}
  .kpi{background:#fff;border:1px solid #D6DEDA;border-radius:10px;padding:12px 14px}
  .kpi .l{font-size:.75rem;letter-spacing:.06em;text-transform:uppercase;color:#5C6B66}
  .kpi .v{font-size:1.7rem;font-weight:700;line-height:1.2;margin-top:2px;font-variant-numeric:tabular-nums}
  .kpi .s{font-size:.82rem;color:#5C6B66}
  .kpi.ok .v{color:#15803D}.kpi.corr .v{color:#B45309}.kpi.nao .v{color:#B91C1C}
  .pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.8rem;font-weight:700}
  .pill.ok{background:#E5F4E9;color:#15803D}.pill.corr{background:#FDF1E3;color:#B45309}.pill.nao{background:#FCE8E8;color:#B91C1C}
  .box{background:#F3F6F5;border-radius:10px;padding:14px 16px;border:1px solid #E3EAE7}
  .box h4{margin:0 0 6px;font-size:.95rem}
  .box p{margin:0;font-size:.9rem;color:#3d4a46}
  .card{background:#fff;border:1px solid #D6DEDA;border-radius:10px;padding:16px 18px;margin-top:.6rem}
  .card ul{margin:.2rem 0 .6rem 1.1rem;padding:0}
  .card li{margin:.15rem 0}
  .muted{color:#5C6B66;font-size:.85rem}
  .mini{font-size:.8rem;color:#3d4a46}
  .mini .t{font-weight:700;color:#5C6B66;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;margin-bottom:4px}
  .mini table{border-collapse:collapse;width:100%}
  .mini th{text-align:left;font-weight:600;color:#5C6B66;border-bottom:1px solid #D6DEDA;padding:2px 4px}
  .mini td{padding:2px 4px;border-bottom:1px solid #EEF2F0}
  section[data-testid="stSidebar"] .block-container{padding-top:1rem}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Dados
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Conferindo as 80 guias...")
def carregar_lote(data_ref, usar_ia):
    return processar_lote(CAMINHO_CSV, CAMINHO_REGRAS, data_ref=data_ref, usar_ia=usar_ia)


@st.cache_resource(show_spinner=False)
def storage():
    return obter_storage()


def conjunto_atual():
    """Lote de agosto + guias importadas pelo site (a importada substitui a de mesmo id)."""
    decisoes, _ = carregar_lote(DATA_REF, IA_LIGADA)
    por_id = {d["id_guia"]: d for d in decisoes}
    importadas = []
    try:
        importadas = storage().listar_importadas()
    except Exception:  # noqa: BLE001
        pass
    for imp in importadas:
        por_id[imp["id_guia"]] = imp
    lista = list(por_id.values())
    versao = carregar_regras(CAMINHO_REGRAS).get("versao")
    return lista, resumir(lista, "data de lançamento de cada guia", versao, IA_LIGADA), len(importadas)


def moeda(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


CLASSE = {OK: "ok", CORRIGIR: "corr", NAO_ENVIAR: "nao"}
ROTULO_CURTO = {OK: "OK", CORRIGIR: "Corrigir", NAO_ENVIAR: "Não enviar"}


def pill(estado):
    return f'<span class="pill {CLASSE.get(estado, "")}">{estado}</span>'


def kpi(label, valor, sub="", classe="", ajuda=""):
    dica = f' title="{ajuda}"' if ajuda else ""
    return (f'<div class="kpi {classe}"{dica}><div class="l">{label}{" ⓘ" if ajuda else ""}</div>'
            f'<div class="v">{valor}</div><div class="s">{sub}</div></div>')


def bloco_erro_amigavel(exc):
    st.error("Não foi possível concluir esta ação, mas o site continua no ar.")
    with st.expander("Detalhe técnico"):
        st.code("".join(traceback.format_exception_only(type(exc), exc)).strip())


def acao_nao_enviar(d):
    """Frase da ação para uma guia NÃO ENVIAR, pelo tipo que a levou lá."""
    tipos = d.get("tipos", [])
    if "cópia de outra guia" in tipos:
        return "É cópia de uma guia já lançada. Descartar esta; enviar as duas seria cobrança em dobro."
    if "paciente optou por particular" in tipos:
        return f"Paciente não quer usar o convênio. Emitir como particular ({moeda(d['valor_reclassificar'])})."
    return (f"O convênio não cobre este procedimento e vai negar. "
            f"Faturar como particular ({moeda(d['valor_reclassificar'])}); o dinheiro não se perde.")


# ---------------------------------------------------------------------------
# Texto colado -> campos (parser determinístico, sem IA)
# ---------------------------------------------------------------------------
def _sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


ALIASES = {
    "id_guia": ["id_guia", "id da guia", "guia", "nº da guia", "numero da guia"],
    "unidade": ["unidade"],
    "data_atendimento": ["data_atendimento", "data do atendimento", "atendimento", "data do atend", "atend"],
    "paciente": ["paciente"],
    "convenio": ["convenio", "convênio", "plano"],
    "carteirinha": ["carteirinha", "carteira", "numero da carteirinha"],
    "cid": ["cid"],
    "procedimento_codigo": ["procedimento_codigo", "codigo do procedimento", "procedimento", "codigo", "código"],
    "numero_autorizacao": ["numero_autorizacao", "numero da autorizacao", "autorizacao", "autorização", "aut"],
    "autorizacao_validade": ["autorizacao_validade", "validade da autorizacao", "validade"],
    "autorizacao_sessoes_limite": ["autorizacao_sessoes_limite", "limite de sessoes", "limite"],
    "sessao_numero_na_autorizacao": ["sessao_numero_na_autorizacao", "sessao", "sessão", "sessao numero", "numero da sessao"],
    "profissional": ["profissional", "fisioterapeuta", "medico", "médico"],
    "profissional_registro": ["profissional_registro", "registro do profissional", "registro", "crefito", "crm"],
    "valor": ["valor", "r$"],
    "observacao_recepcao": ["observacao_recepcao", "observacao", "observação", "obs"],
    "data_lancamento": ["data_lancamento", "data de lancamento", "lancamento", "lançamento"],
}
_ALIAS_INDEX = {_sem_acento(a): campo for campo, lst in ALIASES.items() for a in lst}


def texto_para_campos(texto):
    """Uma linha = um campo ('validade: 30/09/2026'). ';' só separa quando a linha não tem ':'.
    Campo repetido: vale o primeiro e o segundo vai para os ignorados, com aviso."""
    campos, ignorados = {}, []
    for linha in (texto or "").split("\n"):
        pedacos = [linha] if (":" in linha or "=" in linha) else [p for p in linha.split(";")]
        for pedaco in pedacos:
            if ":" not in pedaco and "=" not in pedaco:
                if pedaco.strip():
                    ignorados.append(pedaco.strip())
                continue
            chave, valor = re.split(r"[:=]", pedaco, maxsplit=1)
            alvo = _ALIAS_INDEX.get(_sem_acento(chave.strip()))
            if not alvo:
                ignorados.append(pedaco.strip())
            elif alvo in campos:
                ignorados.append(f"campo repetido, valeu o primeiro: {pedaco.strip()}")
            else:
                campos[alvo] = valor.strip()
    return campos, ignorados


# ---------------------------------------------------------------------------
# Conferir uma guia nova (formulário, texto ou CSV passam por aqui)
# ---------------------------------------------------------------------------
def conferir(campos):
    """Confere sem gravar. Compara com o conjunto atual (lote + importadas)."""
    conjunto, _, _ = conjunto_atual()
    # Guia com id que já está no conjunto = a própria guia reconferida (não é cópia de si mesma).
    ids_dup, nova = duplicatas_de(campos, conjunto)
    decisao = verificar_guia(campos, data_ref=DATA_REF, ids_duplicata=ids_dup, usar_ia=IA_LIGADA,
                             guia_nova=nova)
    # Dados da guia que o painel, a lista e o relatório mostram.
    g = normalizar_guia(campos if isinstance(campos, dict) else {})
    regras = carregar_regras(CAMINHO_REGRAS)
    proc = next((p for p in regras["procedimentos"] if p["codigo"] == g.get("procedimento_codigo")), None)
    decisao.update({
        "unidade": g.get("unidade", ""), "paciente": g.get("paciente", ""),
        "profissional": g.get("profissional", ""),
        "procedimento_codigo": g.get("procedimento_codigo", ""),
        "procedimento_descricao": (proc or {}).get("descricao", g.get("procedimento_descricao", "")),
        "data_atendimento": g.get("data_atendimento", ""),
        "data_lancamento": g.get("data_lancamento", "") or decisao.get("data_referencia", ""),
        "observacao_recepcao": g.get("observacao_recepcao", ""),
    })
    return decisao


def importar(decisoes, origem):
    """Grava as decisões: a guia passa a fazer parte do painel, da lista e do relatório."""
    n = 0
    for d in decisoes:
        storage().salvar_resultado(d, origem=origem)
        n += 1
    return n


def mostrar_decisao(d, titulo=None):
    """Cartão de decisão: usado na guia nova e no detalhe do painel."""
    estado = d["decisao"]
    cab = f"{pill(estado)}&nbsp; <b>{titulo or d.get('id_guia', '')}</b>"
    if estado == OK:
        frase = "Pronta para envio ao convênio."
    elif estado == CORRIGIR:
        frase = (f"Segura {moeda(d['valor_em_risco'])}. Entra se a recepção corrigir antes do envio.")
    else:
        frase = acao_nao_enviar(d)
    partes = [f'<div class="card"><div>{cab}</div><p style="margin:.5rem 0 .2rem">{frase}</p>']
    if d.get("urgente"):
        partes.append(f'<p class="muted">⏰ Prazo de envio vence em {d["dias_para_prazo"]} dia(s).</p>')
    if d.get("motivos"):
        partes.append("<b>Por quê</b><ul>" + "".join(f"<li>{m}</li>" for m in d["motivos"]) + "</ul>")
    if d.get("correcoes"):
        partes.append("<b>O que fazer</b><ul>" + "".join(f"<li>{c}</li>" for c in d["correcoes"]) + "</ul>")
    if d.get("alertas"):
        partes.append("<b>Avisos</b> <span class='muted'>(não reprovam)</span><ul>"
                      + "".join(f"<li>{a}</li>" for a in d["alertas"]) + "</ul>")
    if d.get("normalizacoes"):
        partes.append(f'<p class="muted">Formato corrigido automaticamente: {"; ".join(d["normalizacoes"])}</p>')
    if d.get("sinais"):
        s = {k: v for k, v in d["sinais"].items() if v and not k.startswith("_")}
        partes.append('<p class="muted">IA leu a observação e marcou: '
                      + (json.dumps(s, ensure_ascii=False) if s else "nada que mude a guia") + "</p>")
    if d.get("_gravou") is False:
        partes.append('<p class="muted">Decisão calculada; o histórico não pôde ser gravado agora.</p>')
    partes.append("</div>")
    st.markdown("".join(partes), unsafe_allow_html=True)
    with st.expander("Decisão completa (JSON)"):
        st.code(json.dumps({k: v for k, v in d.items() if not k.startswith("_")},
                           ensure_ascii=False, indent=2, default=str), language="json")


# ---------------------------------------------------------------------------
# Barra lateral: navegação + filtros
# ---------------------------------------------------------------------------
st.sidebar.markdown("### 🩺 Vitalis · Guias")
# Um botão de outra página (ex.: "Top 3 ações" do relatório) pede para abrir a lista já filtrada.
# O pedido é aplicado AQUI, antes de os widgets existirem (o Streamlit não deixa mudar depois).
if "_ir_para" in st.session_state:
    destino = st.session_state.pop("_ir_para")
    st.session_state["pagina"] = destino["pagina"]
    st.session_state["lc_tipo"] = destino.get("tipos", [])
    st.session_state["lc_uni"] = []
    st.session_state["lc_con"] = []
    st.session_state["lc_est"] = []
    st.session_state.pop("lc_dias", None)
pagina = st.sidebar.radio("Página", ["Painel", "Lista de correções", "Conferir guia", "Relatório semanal",
                                     "Regras dos convênios", "MCP", "Documentos"], label_visibility="collapsed",
                          key="pagina")
try:
    _dec_ia, _ = carregar_lote(DATA_REF, IA_LIGADA)
    _lidas = sum(1 for d in _dec_ia if d.get("sinais") and not d["sinais"].get("nao_lida"))
    _mudou = sum(1 for d in _dec_ia if d.get("sinais") and any(
        v for k, v in d["sinais"].items() if k not in ("irrelevante", "nao_lida") and not k.startswith("_")))
    _ia_txt = (f"🟢 ligada · leu {_lidas} observações, {_mudou} mudaram a decisão" if IA_LIGADA
               else "⚪ desligada · observações vão para leitura humana")
except Exception:  # noqa: BLE001
    _ia_txt = "🟢 ligada" if IA_LIGADA else "⚪ desligada"
st.sidebar.markdown(f"<p class='muted'>IA: {_ia_txt}</p>", unsafe_allow_html=True)

# ===========================================================================
# PAINEL
# ===========================================================================
if pagina == "Painel":
    try:
        decisoes, r, n_importadas = conjunto_atual()
        df = pd.DataFrame([{
            "Guia": d["id_guia"], "Unidade": d.get("unidade", ""), "Convênio": d["convenio"],
            "Paciente": d.get("paciente", ""), "Profissional": d.get("profissional", ""),
            "Procedimento": f"{d.get('procedimento_codigo', '')} · {d.get('procedimento_descricao', '')}",
            "Atendimento": d.get("data_atendimento", ""), "Decisão": d["decisao"],
            "Problemas": ", ".join(sorted(set(d.get("tipos", [])))) or "",
            "_tipos": list(set(d.get("tipos", []))),
            "Valor": d.get("valor", 0.0), "R$ em risco": d["valor_em_risco"],
            "R$ reclassificar": d["valor_reclassificar"],
            "Prazo (dias)": d.get("dias_para_prazo"), "_urgente": bool(d.get("urgente")),
        } for d in decisoes])

        # ---- filtros na barra lateral ----
        st.sidebar.markdown("---")
        st.sidebar.markdown("**Filtros**")
        busca = st.sidebar.text_input("Guia ou paciente", "", placeholder="G-2608-0041 ou P-1036")
        f_dec = st.sidebar.multiselect("Decisão", [OK, CORRIGIR, NAO_ENVIAR])
        f_uni = st.sidebar.multiselect("Unidade", sorted(u for u in df["Unidade"].unique() if u))
        f_con = st.sidebar.multiselect("Convênio", sorted(c for c in df["Convênio"].unique() if c))
        f_pro = st.sidebar.multiselect("Profissional", sorted(p for p in df["Profissional"].unique() if p))
        f_prc = st.sidebar.multiselect("Procedimento", sorted(p for p in df["Procedimento"].unique() if p))
        tipos_todos = sorted({t for d in decisoes for t in d.get("tipos", [])})
        f_tip = st.sidebar.multiselect("Tipo de problema", tipos_todos)
        so_urg = st.sidebar.checkbox("Só prazo de envio ≤ 7 dias")

        f = df
        if busca.strip():
            b = busca.strip().lower()
            f = f[f["Guia"].str.lower().str.contains(b, regex=False) | f["Paciente"].str.lower().str.contains(b, regex=False)]
        if f_dec:
            f = f[f["Decisão"].isin(f_dec)]
        if f_uni:
            f = f[f["Unidade"].isin(f_uni)]
        if f_con:
            f = f[f["Convênio"].isin(f_con)]
        if f_pro:
            f = f[f["Profissional"].isin(f_pro)]
        if f_prc:
            f = f[f["Procedimento"].isin(f_prc)]
        if f_tip:
            f = f[f["_tipos"].apply(lambda ts: any(t in ts for t in f_tip))]
        if so_urg:
            f = f[f["_urgente"]]
        filtrado = len(f) != len(df)

        # ---- cabeçalho + números (do recorte filtrado) ----
        st.markdown("# Conferência de guias antes do envio")
        st.markdown('<p class="sub">Cada guia é conferida contra o que o convênio exige e recebe uma decisão com o '
                    'motivo e o que fazer. A IA só lê o que a recepção escreveu à mão; quem decide é a regra.</p>',
                    unsafe_allow_html=True)
        n_ok = int((f["Decisão"] == OK).sum()); n_co = int((f["Decisão"] == CORRIGIR).sum()); n_ne = int((f["Decisão"] == NAO_ENVIAR).sum())
        risco = float(f["R$ em risco"].sum())
        reclass = float(f["R$ reclassificar"].sum())   # cópias valem 0: não é dinheiro a reclassificar
        total_valor = float(f["Valor"].sum())
        ok_valor = float(f.loc[f["Decisão"] == OK, "Valor"].sum())
        urg_valor = float(f.loc[f["_urgente"], "Valor"].sum())
        st.markdown('<div class="kpis">'
                    + kpi("Guias conferidas", len(f), f"{moeda(total_valor)} · 80 de agosto + {n_importadas} importadas"
                          if not filtrado else f"{moeda(total_valor)} no recorte")
                    + kpi("OK", n_ok, f"{moeda(ok_valor)} prontos para envio", "ok",
                          "Guias sem nenhum problema. Podem ir ao convênio.")
                    + kpi("Corrigir", n_co, f"{moeda(risco)} recuperáveis se corrigidas", "corr",
                          "Falta algo que a recepção resolve no sistema antes do envio. O valor entra se corrigir.")
                    + kpi("Não enviar", n_ne, f"{moeda(reclass)} a faturar como particular", "nao",
                          "O convênio não cobre, o paciente pediu particular, ou é cópia de outra guia.")
                    + kpi("Prazo de envio ≤ 7 dias", int(f["_urgente"].sum()), f"{moeda(urg_valor)} a enviar primeiro", "",
                          "Cada guia tem 30 ou 45 dias, contados do atendimento, para chegar ao convênio.")
                    + "</div>", unsafe_allow_html=True)

        col_tab, col_lat = st.columns([3, 1], gap="large")
        with col_lat:
            por_tipo = {}
            for d in decisoes:
                if d["id_guia"] in set(f["Guia"]):
                    for t in set(d.get("tipos", [])):
                        por_tipo[t] = por_tipo.get(t, 0) + 1
            linhas_t = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{n}</td></tr>"
                               for t, n in sorted(por_tipo.items(), key=lambda x: -x[1]))
            st.markdown("<div class='mini'><div class='t'>Problemas por tipo</div>"
                        "<table><tr><th>Tipo de problema</th><th style='text-align:right'>Guias</th></tr>"
                        + (linhas_t or "<tr><td colspan='2'>Nenhum no recorte</td></tr>") + "</table></div>",
                        unsafe_allow_html=True)

        with col_tab:
            st.markdown(f"**{len(f)} guias** {'no filtro' if filtrado else 'no lote'}")
            mostrar = f[["Guia", "Decisão", "Unidade", "Convênio", "Paciente", "Profissional",
                         "Procedimento", "Atendimento", "Problemas", "Valor", "Prazo (dias)"]]
            st.dataframe(mostrar, hide_index=True, use_container_width=True, height=420,
                         column_config={
                             "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
                             "Decisão": st.column_config.TextColumn(width="medium"),
                             "Prazo (dias)": st.column_config.NumberColumn("Dias p/ enviar", format="%d"),
                         })
            st.download_button("Baixar este recorte (CSV)", mostrar.to_csv(index=False).encode("utf-8"),
                               "guias_filtradas.csv", "text/csv")

        st.markdown("## Detalhe de uma guia")
        opcoes = list(f["Guia"])
        if opcoes:
            escolhida = st.selectbox("Escolha a guia", opcoes, label_visibility="collapsed")
            d = next(x for x in decisoes if x["id_guia"] == escolhida)
            c1, c2 = st.columns([1, 2], gap="large")
            with c1:
                st.markdown("<div class='box'><h4>Dados da guia</h4>"
                            f"<p><b>Paciente</b> {d.get('paciente', '')} · <b>Unidade</b> {d.get('unidade', '')}</p>"
                            f"<p><b>Convênio</b> {d['convenio']}</p>"
                            f"<p><b>Procedimento</b> {d.get('procedimento_codigo', '')} · {d.get('procedimento_descricao', '')}</p>"
                            f"<p><b>Profissional</b> {d.get('profissional', '')}</p>"
                            f"<p><b>Atendimento</b> {d.get('data_atendimento', '')} · <b>Lançamento</b> {d.get('data_lancamento', '')}</p>"
                            f"<p><b>Valor</b> {moeda(d.get('valor', 0.0))}</p>"
                            + (f"<p><b>Observação da recepção</b> “{d['observacao_recepcao']}”</p>" if d.get("observacao_recepcao") else "")
                            + "</div>", unsafe_allow_html=True)
            with c2:
                mostrar_decisao(d, titulo=f"{d['id_guia']}")
        else:
            st.info("Nenhuma guia no filtro atual.")
    except Exception as exc:  # noqa: BLE001
        bloco_erro_amigavel(exc)

# ===========================================================================
# LISTA DE CORREÇÕES: o que a recepção de cada unidade precisa fazer hoje
# ===========================================================================
elif pagina == "Lista de correções":
    st.markdown("# Lista de correções")
    st.markdown('<p class="sub">O que cada unidade precisa fazer no sistema de gestão antes do envio, guia por guia. '
                'Depois de corrigir lá, a guia é conferida de novo e vira OK.</p>', unsafe_allow_html=True)
    try:
        decisoes, _, _ = conjunto_atual()
        pend = [d for d in decisoes if d["decisao"] != OK]
        st.sidebar.markdown("---")
        st.sidebar.markdown("**Filtros**")
        unidades = sorted({d.get("unidade", "") for d in pend if d.get("unidade")})
        f_uni = st.sidebar.multiselect("Unidade", unidades, key="lc_uni")
        f_con = st.sidebar.multiselect("Convênio", sorted({d["convenio"] for d in pend}), key="lc_con")
        f_est = st.sidebar.multiselect("Situação", [CORRIGIR, NAO_ENVIAR], key="lc_est")
        tipos_lc = sorted({t for d in pend for t in d.get("tipos", [])})
        f_tipo = st.sidebar.multiselect("Tipo de problema", tipos_lc, key="lc_tipo")
        max_dias = max([d.get("dias_para_prazo") or 0 for d in pend] + [1])
        f_dias = st.sidebar.slider("Dias para enviar (até)", 1, int(max_dias), int(max_dias), key="lc_dias",
                                   help="Mostra só as guias com este número de dias ou menos até o prazo de envio")
        if f_dias < max_dias:
            pend = [d for d in pend if (d.get("dias_para_prazo") or 0) <= f_dias]
        if f_uni:
            pend = [d for d in pend if d.get("unidade") in f_uni]
        if f_con:
            pend = [d for d in pend if d["convenio"] in f_con]
        if f_est:
            pend = [d for d in pend if d["decisao"] in f_est]
        if f_tipo:
            pend = [d for d in pend if any(t in d.get("tipos", []) for t in f_tipo)]
            st.markdown(f"<p class='muted'>Filtrado por tipo de problema: <b>{', '.join(f_tipo)}</b></p>",
                        unsafe_allow_html=True)

        def ordem(d):  # urgência primeiro, depois valor, depois id
            return (0 if d.get("urgente") else 1, -(d.get("valor") or 0), d["id_guia"])

        n_corr = sum(1 for d in pend if d["decisao"] == CORRIGIR)
        n_nao = sum(1 for d in pend if d["decisao"] == NAO_ENVIAR)
        st.markdown('<div class="kpis">'
                    + kpi("Guias na lista", len(pend), "no recorte atual")
                    + kpi("Para corrigir no sistema", n_corr, moeda(sum(d["valor_em_risco"] for d in pend)), "corr")
                    + kpi("Para reclassificar ou excluir", n_nao, moeda(sum(d["valor_reclassificar"] for d in pend)), "nao")
                    + "</div>", unsafe_allow_html=True)

        linhas_csv = []
        for uni in (f_uni or unidades):
            grupo = sorted([d for d in pend if d.get("unidade") == uni], key=ordem)
            if not grupo:
                continue
            st.markdown(f"## Unidade {uni} · {len(grupo)} guias")
            for d in grupo:
                acao = " · ".join(d["correcoes"]) if d["decisao"] == CORRIGIR else acao_nao_enviar(d)
                st.markdown(
                    f'<div class="card" style="padding:12px 16px">'
                    f'<div>{pill(d["decisao"])}&nbsp; <b>{d["id_guia"]}</b> · {d.get("paciente", "")} · {d["convenio"]} · '
                    f'{d.get("procedimento_descricao", "")} · atendimento {d.get("data_atendimento", "")} · {moeda(d.get("valor", 0.0))}'
                    + (f' · <b>⏰ {d["dias_para_prazo"]} dia(s) para o prazo</b>' if d.get("urgente") else "")
                    + f'</div><p style="margin:.4rem 0 0"><b>Fazer:</b> {acao}</p>'
                    f'<p class="muted" style="margin:.2rem 0 0">Por quê: {" · ".join(d["motivos"])}</p></div>',
                    unsafe_allow_html=True)
                linhas_csv.append({"Unidade": uni, "Guia": d["id_guia"], "Paciente": d.get("paciente", ""),
                                   "Convênio": d["convenio"], "Situação": d["decisao"], "Fazer": acao,
                                   "Por quê": " | ".join(d["motivos"]), "Valor": d.get("valor", 0.0)})
        if linhas_csv:
            st.download_button("Baixar a lista (CSV) para imprimir ou mandar no WhatsApp da unidade",
                               pd.DataFrame(linhas_csv).to_csv(index=False).encode("utf-8"),
                               "lista-de-correcoes.csv", "text/csv")
        else:
            st.info("Nada a corrigir no recorte atual.")
    except Exception as exc:  # noqa: BLE001
        bloco_erro_amigavel(exc)

# ===========================================================================
# CONFERIR GUIA
# ===========================================================================
elif pagina == "Conferir guia":
    st.markdown("# Conferir uma guia nova")
    st.markdown('<p class="sub">Aceita data brasileira, vírgula no valor e campos faltando. A guia passa pelo mesmo '
                'motor do lote, é comparada com o lote e com o histórico (cópia) e fica gravada.</p>',
                unsafe_allow_html=True)
    try:
        regras = carregar_regras(CAMINHO_REGRAS)
        nomes = [b["nome"] for b in regras["convenios"]]
        aba_form, aba_texto, aba_csv = st.tabs(["Formulário", "Colar texto", "Enviar CSV"])

        with aba_form:
            with st.form("guia_nova"):
                a, b, c = st.columns(3)
                id_guia = a.text_input("ID da guia", "G-NOVA-0001")
                unidade = b.selectbox("Unidade", ["Centro", "Norte", "Sul"])
                convenio = c.selectbox("Convênio", nomes + ["(outro)"])
                convenio_livre = c.text_input("Nome do convênio (se outro)", "")
                a, b, c = st.columns(3)
                carteirinha = a.text_input("Carteirinha", "")
                cid = b.text_input("CID", "")
                procedimento = c.selectbox("Procedimento", [f"{p['codigo']} · {p['descricao']}" for p in regras["procedimentos"]] + ["(outro código)"])
                proc_livre = c.text_input("Código (se outro)", "")
                a, b, c = st.columns(3)
                data_atendimento = a.text_input("Data do atendimento", "", placeholder="dd/mm/aaaa")
                validade = b.text_input("Validade da autorização", "", placeholder="dd/mm/aaaa")
                data_lanc = c.text_input("Data de lançamento", "", placeholder="dd/mm/aaaa (vazio = hoje)")
                a, b, c = st.columns(3)
                num_aut = a.text_input("Número da autorização", "")
                sessao = b.text_input("Sessão nº na autorização", "")
                valor = c.text_input("Valor", "", placeholder="62,00")
                a, b = st.columns(2)
                registro = a.text_input("Registro do profissional", "")
                obs = b.text_input("Observação da recepção", "")
                enviado = st.form_submit_button("Conferir guia", type="primary")
            if enviado:
                campos = {
                    "id_guia": id_guia, "unidade": unidade,
                    "convenio": convenio_livre if convenio == "(outro)" else convenio,
                    "carteirinha": carteirinha, "cid": cid,
                    "procedimento_codigo": proc_livre if procedimento.startswith("(") else procedimento.split(" · ")[0],
                    "data_atendimento": data_atendimento, "autorizacao_validade": validade,
                    "data_lancamento": data_lanc, "numero_autorizacao": num_aut,
                    "sessao_numero_na_autorizacao": sessao, "valor": valor,
                    "profissional_registro": registro, "observacao_recepcao": obs,
                }
                try:
                    st.session_state["conf_form"] = conferir(campos)
                except Exception as exc:  # noqa: BLE001
                    bloco_erro_amigavel(exc)
            d_form = st.session_state.get("conf_form")
            if d_form:
                mostrar_decisao(d_form)
                if st.button("Importar para o painel", key="imp_form", type="primary"):
                    importar([d_form], "formulario")
                    st.session_state.pop("conf_form", None)
                    st.success(f"{d_form['id_guia']} importada. Já aparece no Painel, na Lista de correções e no Relatório.")
                    st.rerun()

        with aba_texto:
            st.caption("Cole como a recepção escreve, um campo por linha: `convênio: Vitalcard`, "
                       "`validade: 30/09/2026`, `valor: 62,00`, `obs: paciente trouxe autorização nova`...")
            exemplo = ("guia: G-NOVA-0002\nconvênio: Saúde Interior\ncarteirinha: 555123456\n"
                       "procedimento: 50000470\natendimento: 28/08/2026\nvalidade: 20/09/2026\n"
                       "sessão: 4\nregistro: CREFITO-3 156740-F\nvalor: 62,00\n"
                       "obs: Autorizado por telefone, protocolo 990421, aguardando número.")
            texto = st.text_area("Guia colada", exemplo, height=230, label_visibility="collapsed")
            if st.button("Conferir texto colado", type="primary"):
                campos, ignorados = texto_para_campos(texto)
                if ignorados:
                    st.caption("Linhas que não entendi (ignoradas): " + " · ".join(ignorados))
                try:
                    st.session_state["conf_texto"] = conferir(campos)
                except Exception as exc:  # noqa: BLE001
                    bloco_erro_amigavel(exc)
            d_txt = st.session_state.get("conf_texto")
            if d_txt:
                mostrar_decisao(d_txt)
                if st.button("Importar para o painel", key="imp_texto", type="primary"):
                    importar([d_txt], "texto")
                    st.session_state.pop("conf_texto", None)
                    st.success(f"{d_txt['id_guia']} importada. Já aparece no Painel, na Lista de correções e no Relatório.")
                    st.rerun()

        with aba_csv:
            st.caption("CSV com as colunas do dicionário (como o sistema de gestão exporta).")
            arq = st.file_uploader("Arquivo CSV", type=["csv"], label_visibility="collapsed")
            if arq is not None:
                try:
                    conteudo = arq.getvalue().decode("utf-8-sig", errors="replace")
                    linhas_csv = [l for l in csv.DictReader(io.StringIO(conteudo)) if any((v or "").strip() for v in l.values())]
                    chave_arq = f"{arq.name}:{len(conteudo)}"
                    if st.session_state.get("conf_csv_chave") != chave_arq:
                        st.session_state["conf_csv"] = [conferir(l) for l in linhas_csv]
                        st.session_state["conf_csv_chave"] = chave_arq
                    resultados = st.session_state["conf_csv"]
                    n_ok = sum(1 for d in resultados if d["decisao"] == OK)
                    n_co = sum(1 for d in resultados if d["decisao"] == CORRIGIR)
                    n_ne = sum(1 for d in resultados if d["decisao"] == NAO_ENVIAR)
                    st.markdown("**Resultado deste envio**")
                    st.markdown('<div class="kpis">' + kpi("Guias no arquivo", len(resultados))
                                + kpi("OK", n_ok, moeda(sum(d.get("valor", 0.0) for d in resultados if d["decisao"] == OK)), "ok")
                                + kpi("Corrigir", n_co, moeda(sum(d["valor_em_risco"] for d in resultados)), "corr")
                                + kpi("Não enviar", n_ne, moeda(sum(d["valor_reclassificar"] for d in resultados)), "nao")
                                + "</div>", unsafe_allow_html=True)
                    st.dataframe(pd.DataFrame([{
                        "Guia": d["id_guia"], "Convênio": d["convenio"], "Decisão": d["decisao"],
                        "Por quê": " | ".join(d["motivos"]) or "", "O que fazer": " | ".join(d["correcoes"]) or "",
                    } for d in resultados]), use_container_width=True, hide_index=True)
                    if st.button(f"Importar as {len(resultados)} guias para o painel", key="imp_csv", type="primary"):
                        n = importar(resultados, "csv")
                        st.session_state.pop("conf_csv", None)
                        st.session_state.pop("conf_csv_chave", None)
                        st.success(f"{n} guias importadas. Já aparecem no Painel, na Lista de correções e no Relatório.")
                        st.rerun()
                except Exception as exc:  # noqa: BLE001
                    bloco_erro_amigavel(exc)

        st.markdown("## Guias importadas neste site")
        st.markdown("<p class='muted'>Guias que você importou pelo formulário, por texto ou por CSV. Elas fazem parte "
                    "do Painel, da Lista de correções e do Relatório junto com as 80 de agosto. Importar de novo uma guia "
                    "com o mesmo id substitui a decisão anterior.</p>", unsafe_allow_html=True)
        try:
            regs = storage().listar_importadas()
            n_ok = sum(1 for x in regs if x["decisao"] == OK)
            n_co = sum(1 for x in regs if x["decisao"] == CORRIGIR)
            n_ne = sum(1 for x in regs if x["decisao"] == NAO_ENVIAR)
            st.markdown('<div class="kpis">' + kpi("Importadas", len(regs)) + kpi("OK", n_ok, "", "ok")
                        + kpi("Corrigir", n_co, moeda(sum(x.get("valor_em_risco", 0) for x in regs)), "corr")
                        + kpi("Não enviar", n_ne, moeda(sum(x.get("valor_reclassificar", 0) for x in regs)), "nao")
                        + "</div>", unsafe_allow_html=True)
            if regs:
                st.dataframe(pd.DataFrame([{
                    "Quando (UTC)": x["criado_em"], "Origem": x["origem"], "Guia": x["id_guia"],
                    "Convênio": x["convenio"], "Decisão": x["decisao"],
                    "Por quê": " | ".join(x.get("motivos", [])) or "",
                } for x in regs]), use_container_width=True, hide_index=True)
            else:
                st.info("Nenhuma guia importada ainda.")
            with st.expander("Remover todas as guias importadas (o lote de agosto não muda)"):
                confirmar = st.checkbox("Confirmo que quero remover todas as importadas", key="confirma_limpar")
                if st.button("Remover importadas", disabled=not confirmar):
                    n = storage().apagar_tudo()
                    st.success(f"{n} registros removidos.")
                    st.rerun()
        except Exception as exc:  # noqa: BLE001
            bloco_erro_amigavel(exc)
    except Exception as exc:  # noqa: BLE001
        bloco_erro_amigavel(exc)

# ===========================================================================
# RELATÓRIO DE TERÇA
# ===========================================================================
elif pagina == "Relatório semanal":
    try:
        decisoes, r_total, _ = conjunto_atual()

        def semana_de(iso):
            try:
                d = date.fromisoformat(iso)
            except (ValueError, TypeError):
                return None
            ini = d - timedelta(days=d.weekday())
            return ini, ini + timedelta(days=6)

        semanas, sem_data = {}, []
        for d in decisoes:
            sem = semana_de(d.get("data_lancamento"))
            if sem:
                semanas.setdefault(sem, []).append(d)
            else:
                sem_data.append(d)   # data ilegível: entra só no total do mês
        rotulos = {f"Semana de {i.strftime('%d/%m')} a {f.strftime('%d/%m')}": k for k, (i, f) in
                   [((i, f), (i, f)) for (i, f) in sorted(semanas)]}
        total = r_total["total_conferidas"]
        opcoes = [f"Tudo ({total} guias)"] + list(rotulos)
        st.markdown("# Relatório semanal · conferência de guias antes do envio")
        st.markdown(f'<p class="sub">Clínica Vitalis · {total} guias conferidas (80 de agosto + importadas)</p>',
                    unsafe_allow_html=True)
        escolha = st.selectbox("Filtro por data:", opcoes, help="Semanas pela data de lançamento da guia")
        with st.expander("Como ler este relatório"):
            st.markdown(
                "- **OK**: guia sem problema; pode ir ao convênio.\n"
                "- **Corrigir**: falta algo que a recepção resolve no sistema de gestão antes do envio. "
                "**Recuperável se corrigir** é a soma dessas guias: dinheiro que entra se a correção for feita.\n"
                "- **Não enviar**: o convênio não cobre o procedimento, o paciente pediu particular, ou é cópia "
                "de outra guia. **Faturar particular** é a soma dessas guias (cópias valem zero).\n"
                "- **Prazo de envio**: cada guia tem 30 ou 45 dias, contados do atendimento, para chegar ao convênio.\n"
                "- **Por unidade / Por convênio**: os mesmos números, separados por unidade da clínica e por convênio.")
        if escolha.startswith("Tudo"):
            r, periodo = r_total, "todo o período"
        else:
            sub = semanas[rotulos[escolha]]
            r = resumir(sub, r_total["data_referencia"], r_total.get("versao_regras"), r_total.get("com_ia"))
            periodo = escolha.lower()
        texto = montar_texto(r, periodo=periodo)
        corpo = texto.split("## O quadro da semana", 1)[1]           # título e subtítulo já estão acima
        antes, _, depois = corpo.partition("## 5. Top 3 ações da semana")
        st.markdown(("## O quadro da semana" + antes).replace("R$", "R\\$"))   # "$...$" viraria fórmula
        st.markdown("## 5. Top 3 ações da semana")
        from gerar_relatorio import ACAO_POR_TIPO
        for i, (tipo, n) in enumerate(list(r["problemas_por_tipo"].items())[:3], 1):
            frase = ACAO_POR_TIPO.get(tipo, f"Resolver as {{n}} guias de '{tipo}'.").format(n=n)
            c_txt, c_btn = st.columns([4, 1])
            c_txt.markdown(f"**{i}.** {frase}")
            if c_btn.button("Ver na lista de correções", key=f"acao_{i}", use_container_width=True):
                st.session_state["_ir_para"] = {"pagina": "Lista de correções", "tipos": [tipo]}
                st.rerun()
        rodape = "_" + depois.split("\n\n_", 1)[1] if "\n\n_" in depois else ""   # só a nota "Como ler", sem repetir as ações
        st.markdown(rodape.replace("R$", "R\\$"))
        st.download_button("Baixar este relatório (Markdown)", texto.encode("utf-8"),
                           "relatorio-semanal.md", "text/markdown")
    except Exception as exc:  # noqa: BLE001
        bloco_erro_amigavel(exc)

# ===========================================================================
# MCP: a página para pessoas (estilo "Copy for AI" + "Open in ...")
# ===========================================================================
elif pagina == "MCP":
    from urllib.parse import quote

    MCP_URL = "https://vitalis.geaia.com/mcp"
    MENSAGEM_IA = (
        f"Conecte-se ao servidor MCP da Clínica Vitalis em {MCP_URL} (streamable HTTP, sem login). "
        "Ele confere guias de convênio antes do envio. Ferramentas: consultar_regra(convenio, "
        "procedimento_codigo), verificar_guia(guia) e resumo_lote(). Quando eu colar uma guia, monte o "
        "objeto guia com os campos que eu der (convenio, carteirinha, cid, procedimento_codigo, "
        "numero_autorizacao, autorizacao_validade, sessao_numero_na_autorizacao, profissional_registro, "
        "valor, data_atendimento, data_lancamento, observacao_recepcao), chame verificar_guia e responda "
        "em até 6 linhas: decisão (OK, CORRIGIR ou NÃO ENVIAR), por quê e o que fazer. Nunca aprove por "
        "conta própria: quem decide é a ferramenta."
    )
    REPO_URL = os.environ.get("VITALIS_REPO_URL", "https://github.com/leticiamazzonetto/vitalis-conferencia-guias")
    try:
        with open(os.path.join(RAIZ, "docs", "llms.md"), "rb") as _f:
            LLMS_MD = _f.read()
    except OSError:
        LLMS_MD = b""

    st.markdown("# Conectar o fiscal ao seu assistente de IA")
    st.markdown('<p class="sub">Um clique e o Claude, o ChatGPT ou o Cursor passam a conferir guias com as mesmas '
                'regras deste site. Nada para instalar.</p>', unsafe_allow_html=True)

    b1, b2, b3, b4, b5 = st.columns(5)
    b1.link_button("Abrir no Claude", f"https://claude.ai/new?q={quote(MENSAGEM_IA)}", use_container_width=True)
    b2.link_button("Abrir no ChatGPT", f"https://chatgpt.com/?q={quote(MENSAGEM_IA)}", use_container_width=True)
    b3.link_button("Abrir no Perplexity", f"https://www.perplexity.ai/search/new?q={quote(MENSAGEM_IA)}",
                   use_container_width=True)
    b4.link_button("Abrir no GitHub", REPO_URL, use_container_width=True)
    if LLMS_MD:
        b5.download_button("Baixar llms.md", LLMS_MD, "vitalis-llms.md", "text/markdown",
                           use_container_width=True, help="Texto completo para modelos de linguagem: ferramentas, regras, formato de resposta")

    st.markdown("**Ou copie e cole no seu assistente** (ícone de copiar no canto do bloco). Para dar ao modelo o "
                "contexto completo, envie também o arquivo `llms.md`.")
    st.code(MENSAGEM_IA, language="text", wrap_lines=True)

    st.markdown("## Como usar no dia a dia para conferir guias")
    st.markdown('<p class="sub">Quatro passos. O primeiro se faz uma vez só.</p>', unsafe_allow_html=True)
    p1, p2 = st.columns(2, gap="large")
    with p1:
        st.markdown("<div class='box'><h4>1. Conectar o fiscal ao seu assistente (uma vez)</h4>"
                    "<p><b>Claude (claude.ai):</b> Configurações › Conectores › Adicionar conector personalizado › "
                    f"cole <code>{MCP_URL}</code> › Adicionar. Sem login, sem chave.</p>"
                    "<p><b>ChatGPT:</b> Configurações › Conectores › Criar (modo desenvolvedor) › cole o mesmo "
                    "endereço.</p>"
                    "<p><b>Codex, Kimi, Cursor, Gemini e outros:</b> mesmo caminho, \"MCP servers\" ou "
                    "\"Conectores\" nas configurações, colando o endereço.</p>"
                    "<p><b>Claude Code:</b> uma linha no terminal:</p></div>", unsafe_allow_html=True)
        st.code(f"claude mcp add --transport http vitalis-guias {MCP_URL}", language="bash")
        st.markdown("<div class='box'><h4>2. Dar ao assistente o roteiro da recepção (a Skill)</h4>"
                    "<p>Baixe a Skill abaixo e anexe o arquivo na conversa, ou cole o conteúdo dele nas "
                    "instruções do seu Projeto (Claude) ou do seu GPT (ChatGPT). Ela ensina o assistente a "
                    "entender a guia colada de qualquer jeito e a responder sempre no mesmo formato.</p></div>",
                    unsafe_allow_html=True)
        try:
            with open(os.path.join(RAIZ, ".claude", "skills", "conferir-guia", "SKILL.md"), "rb") as _f:
                st.download_button("Baixar a Skill (SKILL.md)", _f.read(), "SKILL.md", "text/markdown",
                                   use_container_width=True)
        except OSError:
            st.caption("Skill não encontrada no servidor.")
    with p2:
        st.markdown("<div class='box'><h4>3. Colar a guia do jeito que saiu da tela</h4>"
                    "<p>Não precisa organizar nada. Escreva \"confere essa guia:\" e cole. Data com barra, vírgula no "
                    "valor e campo faltando não são problema.</p></div>", unsafe_allow_html=True)
        st.markdown("<div class='box'><h4>4. Ler a resposta e agir no sistema de gestão</h4>"
                    "<p>🟢 <b>OK</b>: envie. 🟠 <b>CORRIGIR</b>: faça o que está em \"Fazer\" no sistema de gestão e "
                    "confira de novo. 🔴 <b>NÃO ENVIAR</b>: fature como particular ou descarte a cópia. "
                    "O assistente nunca aprova sozinho; quem decide é a regra do convênio.</p></div>",
                    unsafe_allow_html=True)

    st.markdown("## Depois de conectar, é só colar a guia")
    st.code("confere essa guia: SI, carteirinha 555123456, sessão musculoesquelética, atend 28/08, "
            "validade 20/09, sessão 4, CREFITO-3 156740-F, 62,00. Obs: autorizado por telefone, "
            "protocolo 990421, aguardando número.", language="text", wrap_lines=True)
    st.markdown("<div class='box'><p>🟠 <b>CORRIGIR</b> · Saúde Interior · R$ 62,00<br>"
                "<b>Por quê:</b> autorização verbal (protocolo 990421) sem número lançado; o Saúde Interior aceita "
                "verbal por 5 dias úteis (até 04/09).<br><b>Fazer:</b> lançar o número definitivo da autorização "
                "até 04/09.</p></div>", unsafe_allow_html=True)

    st.markdown("## O que o assistente consegue fazer")
    st.markdown("<div class='kpis'>"
                "<div class='kpi'><div class='l'>consultar_regra</div><div class='s' style='margin-top:6px'>"
                "O que cada convênio exige e cobre: campos obrigatórios, limite de sessões, prazo de envio.</div></div>"
                "<div class='kpi'><div class='l'>verificar_guia</div><div class='s' style='margin-top:6px'>"
                "Confere uma guia como a recepção escreveu e devolve OK, CORRIGIR ou NÃO ENVIAR, por quê e o que fazer.</div></div>"
                "<div class='kpi'><div class='l'>resumo_lote</div><div class='s' style='margin-top:6px'>"
                "Os números do mês: quantas guias, quantas com problema, de que tipo, quanto dinheiro.</div></div>"
                "</div>", unsafe_allow_html=True)

    with st.expander("Ver um exemplo real de resposta de cada ferramenta"):
        try:
            ex_regra = consultar_regra("Plano Bem", "20103301")
            ex_guia = verificar_guia({"id_guia": "G-EXEMPLO", "convenio": "Vitalcard", "carteirinha": "123456789",
                                      "cid": "", "procedimento_codigo": "50000470", "numero_autorizacao": "AUT000001",
                                      "autorizacao_validade": "30/09/2026", "sessao_numero_na_autorizacao": "3",
                                      "profissional_registro": "CREFITO-3 000000-F", "valor": "62,00",
                                      "data_atendimento": "28/08/2026"}, usar_ia=False)
            _, ex_resumo = carregar_lote(DATA_REF, IA_LIGADA)
            t1, t2, t3 = st.tabs(["consultar_regra", "verificar_guia", "resumo_lote"])
            with t1:
                st.code('consultar_regra(convenio="Plano Bem", procedimento_codigo="20103301")', language="python")
                st.code(json.dumps(ex_regra, ensure_ascii=False, indent=2), language="json")
            with t2:
                st.code('verificar_guia(guia={"convenio": "Vitalcard", "cid": "", "procedimento_codigo": "50000470", '
                        '"autorizacao_validade": "30/09/2026", "valor": "62,00", "data_atendimento": "28/08/2026"})',
                        language="python", wrap_lines=True)
                st.code(json.dumps({k: v for k, v in ex_guia.items() if k in
                                    ("decisao", "motivos", "correcoes", "alertas", "valor", "valor_em_risco",
                                     "valor_reclassificar", "urgente", "dias_para_prazo", "normalizacoes")},
                                   ensure_ascii=False, indent=2), language="json")
            with t3:
                st.code("resumo_lote()", language="python")
                st.code(json.dumps({k: ex_resumo[k] for k in
                                    ("total_conferidas", "ok", "corrigir", "nao_enviar", "valor_ok_total",
                                     "valor_em_risco_total", "valor_reclassificar_total", "problemas_por_tipo")},
                                   ensure_ascii=False, indent=2), language="json")
        except Exception as exc:  # noqa: BLE001
            bloco_erro_amigavel(exc)

    with st.expander("Outras formas de conectar (Claude Desktop, servidor local, endereço)"):
        st.markdown("**Claude Desktop** (`claude_desktop_config.json`), apontando para o servidor publicado:")
        st.code(json.dumps({"mcpServers": {"vitalis-guias": {"url": MCP_URL}}}, indent=2), language="json")
        st.markdown("**Rodar o servidor no seu computador** (a partir do repositório), em qualquer assistente que "
                    "aceite MCP por stdio: instale e registre o comando abaixo no arquivo de MCP do seu assistente "
                    "(`command: python`, `args: [\"mcp_server/server.py\"]`). No Claude Code o `.mcp.json` da raiz já faz isso.")
        st.code("pip install -r requirements.txt\npython mcp_server/server.py", language="bash")
        st.markdown(f"**Endereço para máquinas:** `{MCP_URL}` (streamable HTTP). Abrir no navegador não mostra "
                    "nada útil: é um protocolo para assistentes, não uma página.")
    st.markdown("<p class='muted'>A regra é uma só: <code>motor.py</code>. O site, o MCP e a Skill chamam a mesma "
                "função. O MCP é só a tomada.</p>", unsafe_allow_html=True)

# ===========================================================================
# DOCUMENTOS: o que a clínica usa no dia a dia, num lugar só
# ===========================================================================
elif pagina == "Documentos":
    st.markdown("# Documentos")
    st.markdown('<p class="sub">O que a clínica usa no dia a dia: a Skill da recepção, as regras dos convênios, '
                'o modelo de planilha para conferir em lote e a instrução que a IA recebe.</p>',
                unsafe_allow_html=True)

    def _ler(rel):
        try:
            with open(os.path.join(RAIZ, *rel.split("/")), "rb") as f:
                return f.read()
        except OSError:
            return None

    documentos = [
        ("Skill da recepção (SKILL.md)", ".claude/skills/conferir-guia/SKILL.md", "SKILL.md",
         "O roteiro que o seu assistente de IA segue quando você cola uma guia: ele organiza os campos, "
         "consulta o fiscal e responde OK, CORRIGIR ou NÃO ENVIAR com o que fazer. Como usar: página MCP, "
         "\"Como usar no dia a dia\"."),
        ("Regras dos convênios", "dados/regras_convenio.json", "regras_convenio.json",
         "O que cada convênio exige (campos obrigatórios, limite de sessões, prazo de envio) e cobre. É o "
         "arquivo que o fiscal consulta; convênio novo entra aqui, sem mudar o sistema."),
        ("Modelo de planilha para conferir em lote (CSV)", "docs/modelo-guias.csv", "modelo-guias.csv",
         "As colunas que a página \"Conferir guia › Enviar CSV\" espera, com uma linha de exemplo. Exporte do "
         "sistema de gestão neste formato e envie."),
        ("Instrução que a IA recebe para ler a observação da recepção", "prompts/observacao.md",
         "instrucao-ia-observacao.md",
         "Quando a recepcionista escreve uma observação na guia (ex.: \"paciente trouxe autorização nova, "
         "validade 30/09\"), a IA lê esse texto e marca o que ele significa para a regra. Este é o texto "
         "exato que a IA recebe. Está aqui por transparência: você vê o que ela é orientada a fazer e o que "
         "ela nunca decide."),
        ("Documentação técnica do projeto (README)", "README.md", "README.md",
         "Como o sistema foi construído, com quais ferramentas e por quê. Para quem for dar manutenção."),
    ]
    for titulo, rel, nome, desc in documentos:
        conteudo = _ler(rel)
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"**{titulo}**  \n<span class='muted'>{desc}</span>", unsafe_allow_html=True)
        if conteudo is None:
            c2.caption("arquivo não encontrado")
        else:
            c2.download_button("Baixar", conteudo, nome, key=f"dl_{nome}", use_container_width=True)
        st.markdown("<hr style='margin:.3rem 0;border:0;border-top:1px solid #EEF2F0'>", unsafe_allow_html=True)
    st.markdown("<p class='muted'>Conectar um assistente de IA e baixar o texto completo para modelos: página MCP.</p>",
                unsafe_allow_html=True)

# ===========================================================================
# REGRAS DOS CONVÊNIOS
# ===========================================================================
else:
    st.markdown("# Regras dos convênios")
    st.markdown('<p class="sub">A fonte de verdade do motor. Convênio novo = bloco novo no arquivo de regras, sem mudar código. '
                'É o mesmo que a ferramenta <code>consultar_regra</code> do MCP devolve.</p>', unsafe_allow_html=True)
    try:
        regras = carregar_regras(CAMINHO_REGRAS)
        nomes = [b["nome"] for b in regras["convenios"]]
        procs = {p["codigo"]: p for p in regras["procedimentos"]}
        conv = st.selectbox("Convênio", nomes)
        info = consultar_regra(conv, regras=regras)
        c1, c2 = st.columns(2, gap="large")
        with c1:
            st.markdown("<div class='box'><h4>O que exige</h4>"
                        + "<p><b>Campos obrigatórios:</b> " + ", ".join(info["campos_obrigatorios"]) + "</p>"
                        + f"<p><b>Limite de sessões por autorização:</b> {info['limite_sessoes_por_autorizacao']}</p>"
                        + f"<p><b>Prazo de envio:</b> {info['prazo_envio_dias']} dias do atendimento</p>"
                        + f"<p><b>Validade máxima da autorização:</b> {info['validade_maxima_autorizacao_dias']} dias "
                          "<span class='muted'>(não verificável: o CSV não tem a data de concessão)</span></p>"
                        + f"<p><b>Observação do convênio:</b> {info['observacao']}</p>"
                        + f"<p class='muted'>Regras versão {info['versao_regras']}</p></div>", unsafe_allow_html=True)
        with c2:
            st.markdown("<div class='box'><h4>O que cobre</h4>"
                        + "".join(f"<p>{'🟢' if c in info['procedimentos_cobertos'] else '🔴'} {c} · {p['descricao']} · {moeda(p['valor_referencia'])}</p>"
                                  for c, p in procs.items())
                        + "</div>", unsafe_allow_html=True)
    except Exception as exc:  # noqa: BLE001
        bloco_erro_amigavel(exc)
