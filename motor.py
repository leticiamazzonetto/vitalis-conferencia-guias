"""
motor.py — Camada 2 (determinística e pura) do verificador de guias da Clínica Vitalis.

É o coração da solução: recebe UMA guia já normalizada, as regras do convênio e,
opcionalmente, os SINAIS que a IA extraiu da observação da recepção, e devolve uma
decisão auditável. Não usa IA, não acessa rede, não lê disco. Só compara datas,
números e listas. Cada veredito é explicável linha a linha.

Contrato:
    verificar(guia_normalizada, regras, data_ref=None, ids_duplicata=None, sinais=None, guia_nova=False) -> Decisao

Decisao (dict):
    {
      "id_guia": str,
      "convenio": str,
      "decisao": "OK" | "CORRIGIR" | "NÃO ENVIAR",
      "motivos": [str, ...],        # TODOS os problemas encontrados, não só o primeiro
      "correcoes": [str, ...],      # o que a recepção faz para resolver cada motivo
      "alertas": [str, ...],        # avisos que não reprovam (urgência, divergência de dado)
      "tipos": [str, ...],          # categorias dos motivos (para o relatório)
      "valor": float,               # valor da guia (0.0 se ilegível)
      "valor_em_risco": float,      # valor da guia quando CORRIGIR (dinheiro recuperável)
      "valor_reclassificar": float, # valor da guia quando NÃO ENVIAR (sai do convênio)
      "urgente": bool,              # a menos de 7 dias de perder o prazo de envio
      "dias_para_prazo": int|None,  # dias que restam para a guia chegar ao convênio
    }

Os três estados (decisão do projeto, nomeados pela AÇÃO da clínica):
  - OK          : pronta para enviar.
  - CORRIGIR    : falta algo que a recepção resolve antes do envio (ou a observação
                  indica que a correção já existe no balcão).
  - NÃO ENVIAR  : não é pendência da recepção. Reclassificar (faturar particular) ou
                  descartar (cópia de outra guia). Insistir não traz o dinheiro.
  Prioridade quando há vários motivos: NÃO ENVIAR > CORRIGIR > OK.

Princípios:
  - Fonte de verdade é regras_convenio.json, nunca o que a recepção digitou. O limite de
    sessões vem do JSON; a coluna do CSV só gera alerta se divergir.
  - Campos obrigatórios conferidos POR convênio (CID é exigido no Vitalcard e no Plano
    Bem, não no Saúde Interior).
  - Duplicata nunca some em silêncio: a cópia (id maior) vira NÃO ENVIAR apontando a
    original; a original recebe um alerta. O valor conta UMA vez por par.
  - Prazo de envio: o JSON define "dias, contados da data do atendimento, para a guia
    CHEGAR ao convênio". Medimos contra a data de referência da conferência: no lote de
    agosto, a data de lançamento de cada guia (orientação da Expert); numa guia nova, hoje.
    O último dia do prazo ainda vale; "perdido" é só depois dele.
  - A IA não decide. Ela só transforma o texto da recepção em sinais (caixinhas); este
    motor decide com as caixinhas marcadas. Sem IA, a observação vira CORRIGIR "ler".
"""

from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Estados
# ---------------------------------------------------------------------------
OK = "OK"
CORRIGIR = "CORRIGIR"
NAO_ENVIAR = "NÃO ENVIAR"

DIAS_ALERTA_URGENTE = 7          # a menos de 7 dias do prazo de envio = urgente
DIAS_UTEIS_AUTORIZACAO_VERBAL = 5  # padrão; o JSON do convênio pode trazer autorizacao_verbal_dias_uteis

# ---------------------------------------------------------------------------
# Categorias de problema (rótulos usados no relatório de terça).
# ---------------------------------------------------------------------------
TIPO_DADO_INVALIDO = "dado inválido"
TIPO_CONVENIO_DESCONHECIDO = "convênio desconhecido"
TIPO_CAMPO_OBRIGATORIO = "campo obrigatório faltando"
TIPO_AUTORIZACAO_VENCIDA = "autorização vencida"
TIPO_AUTORIZACAO_NOVA = "autorização nova a lançar"
TIPO_AUTORIZACAO_VERBAL = "autorização verbal a regularizar"
TIPO_SESSAO_ACIMA_LIMITE = "sessão acima do limite"
TIPO_NAO_COBERTO = "procedimento não coberto"
TIPO_CODIGO_ERRADO = "código do procedimento errado"
TIPO_PARTICULAR = "paciente optou por particular"
TIPO_PRAZO_ENVIO = "prazo de envio perdido"
TIPO_DUPLICATA = "cópia de outra guia"
TIPO_OBSERVACAO = "observação da recepção requer leitura"
TIPO_OBSERVACAO_NAO_LIDA = "observação não lida pela IA"
TIPO_PROCEDIMENTO_FORA_TABELA = "código do procedimento fora da tabela"

# Quais tipos levam a NÃO ENVIAR (os demais levam a CORRIGIR).
TIPOS_NAO_ENVIAR = {TIPO_NAO_COBERTO, TIPO_PARTICULAR, TIPO_DUPLICATA}

# Rótulo amigável de cada campo obrigatório, para a mensagem à recepção.
NOME_CAMPO = {
    "numero_autorizacao": "número da autorização",
    "autorizacao_validade": "validade da autorização",
    "profissional_registro": "registro do profissional",
    "carteirinha": "carteirinha",
    "cid": "CID",
}

# Observações que a recepção escreve o tempo todo e NÃO mudam o veredito.
# Usadas SÓ quando a IA está desligada (modo sem sinais). Com IA, quem diz se a
# observação é irrelevante é o sinal `irrelevante`.
OBSERVACOES_TRIVIAIS = {
    "trouxe exame novo, anexado ao prontuário.",
    "pediu recibo para reembolso do plano.",
    "paciente chegou 10 min atrasado.",
    "confirmado pelo whatsapp na véspera.",
}


def _regra_convenio(regras, nome_convenio):
    """Localiza o bloco do convênio dentro do JSON de regras. None se não existir."""
    alvo = (str(nome_convenio) if nome_convenio is not None else "").strip().lower()
    for bloco in regras.get("convenios", []):
        if bloco.get("nome", "").strip().lower() == alvo:
            return bloco
    return None


def _procedimento(regras, codigo):
    for p in regras.get("procedimentos", []):
        if p.get("codigo") == codigo:
            return p
    return None


def _canon(texto):
    """Minúsculas, espaços únicos, sem pontuação final: 'Pediu recibo...' == 'pediu recibo'."""
    return " ".join((texto or "").lower().split()).rstrip(" .!;,")


_TRIVIAIS_CANON = {_canon(t) for t in OBSERVACOES_TRIVIAIS}


def observacao_trivial(texto):
    """True quando a observação é rotina (modo sem IA). Vazio conta como trivial."""
    limpo = _canon(texto)
    return limpo == "" or limpo in _TRIVIAIS_CANON


def _data(iso):
    try:
        return date.fromisoformat(iso) if iso else None
    except (ValueError, TypeError):
        return None


def _dias_entre(iso_inicio, iso_fim):
    """fim - início, em dias. None se alguma data faltar ou for inválida."""
    d1, d2 = _data(iso_inicio), _data(iso_fim)
    if d1 is None or d2 is None:
        return None
    return (d2 - d1).days


def somar_dias_uteis(iso, dias_uteis):
    """Soma N dias úteis (segunda a sexta) a uma data ISO. Feriados não considerados."""
    d = _data(iso)
    if d is None:
        return None
    restantes = dias_uteis
    while restantes > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            restantes -= 1
    return d.isoformat()


def _id_num(id_guia):
    """Extrai a parte numérica final do id (G-2608-0057 -> 57) para ordenar o par."""
    try:
        return int(str(id_guia).rsplit("-", 1)[-1])
    except ValueError:
        return 0


def _ordem_id(id_guia):
    """Ordem total: número no fim do id e, em empate (ids sem número), o texto."""
    return (_id_num(id_guia), str(id_guia))


def verificar(guia, regras, data_ref=None, ids_duplicata=None, sinais=None, guia_nova=False):
    """
    Confere UMA guia normalizada contra as regras do seu convênio.

    Parâmetros:
      guia          : dict já passado pelo normalizador (tem _erros e _chave_dup).
      regras        : dict carregado de regras_convenio.json.
      data_ref      : data ISO da conferência (o "hoje"). Usada no PRAZO DE ENVIO:
                      quantos dias restam para a guia chegar ao convênio.
      ids_duplicata : ids de OUTRAS guias com a mesma chave desta.
      sinais        : dict extraído da observação da recepção pela IA (ver observacao.py).
                      None = IA desligada (a observação não trivial vira CORRIGIR "ler").
      guia_nova     : True quando a guia está sendo conferida DEPOIS das outras (site, MCP):
                      se houver igual no lote ou no histórico, esta é a cópia. False no
                      lote, onde a original é a de id menor.

    Devolve a Decisao (dict). Reporta TODOS os motivos, não só o primeiro.
    """
    ids_duplicata = ids_duplicata or []
    sinais = sinais or {}
    id_guia = guia.get("id_guia", "")
    convenio = guia.get("convenio", "")
    valor = guia.get("valor")

    motivos, correcoes, alertas, tipos = [], [], [], []
    urgente = False
    dias_para_prazo = None

    def reprovar(tipo, motivo, correcao):
        tipos.append(tipo)
        motivos.append(motivo)
        correcoes.append(correcao)

    # --- 0) Erros de dado detectados na normalização (data/valor ilegível). ---
    for erro in guia.get("_erros", []):
        reprovar(TIPO_DADO_INVALIDO,
                 f"dado ilegível na guia: {erro}",
                 "corrigir o campo no sistema e reenviar a guia para conferência")

    # --- 1) Convênio existe no JSON de regras? ---
    regra = _regra_convenio(regras, convenio)
    if regra is None:
        reprovar(TIPO_CONVENIO_DESCONHECIDO,
                 f"convênio '{convenio or '(vazio)'}' não está no cadastro de regras",
                 "conferir o nome do convênio ou cadastrar as regras dele antes do envio")
        return _montar_decisao(id_guia, convenio, motivos, correcoes, alertas, tipos,
                               valor, urgente, dias_para_prazo)

    nome = regra["nome"]
    da = guia.get("data_atendimento")

    # --- 2) Campos obrigatórios POR convênio (com a exceção da autorização verbal). ---
    for campo in regra.get("campos_obrigatorios", []):
        if guia.get(campo) not in (None, ""):
            continue
        rotulo = NOME_CAMPO.get(campo, campo)
        if campo == "numero_autorizacao" and sinais.get("protocolo_verbal"):
            protocolo = sinais["protocolo_verbal"]
            dias_verbal = regra.get("autorizacao_verbal_dias_uteis") or DIAS_UTEIS_AUTORIZACAO_VERBAL
            if "verbal" in (regra.get("observacao") or "").lower():
                limite = somar_dias_uteis(da, dias_verbal)
                estourou = bool(data_ref and limite and data_ref > limite)
                ate = f" (até {limite})" if limite else ""
                reprovar(TIPO_AUTORIZACAO_VERBAL,
                         f"autorização verbal (protocolo {protocolo}) sem número lançado; "
                         f"{nome} aceita verbal por {dias_verbal} dias úteis{ate}"
                         + (" e o prazo já passou" if estourou else ""),
                         (f"lançar o número definitivo da autorização até {limite}" if limite
                          else "lançar o número definitivo da autorização antes do envio")
                         if not estourou else
                         "pedir nova autorização: o prazo da verbal já passou")
            else:
                reprovar(TIPO_CAMPO_OBRIGATORIO,
                         f"campo obrigatório ausente para {nome}: {rotulo} "
                         f"(protocolo verbal {protocolo} não vale: {nome} não aceita verbal)",
                         "obter o número da autorização junto ao convênio antes do envio")
            continue
        reprovar(TIPO_CAMPO_OBRIGATORIO,
                 f"campo obrigatório ausente para {nome}: {rotulo}",
                 f"preencher {rotulo} antes do envio")

    # --- 3) Autorização válida: validade >= data do atendimento. ---
    val = guia.get("autorizacao_validade")
    if da and val:
        dias = _dias_entre(da, val)
        if dias is not None and dias < 0:
            validade_nova = sinais.get("validade_nova")
            if sinais.get("autorizacao_nova") and validade_nova and validade_nova >= da:
                reprovar(TIPO_AUTORIZACAO_NOVA,
                         f"autorização lançada está vencida (validade {val} antes do "
                         f"atendimento {da}), mas a recepção anotou autorização nova "
                         f"com validade {validade_nova}",
                         "lançar o número da autorização nova no sistema antes do envio")
            else:
                complemento = ""
                if sinais.get("remarcada_de"):
                    complemento = (f"; a sessão foi remarcada de {sinais['remarcada_de']} "
                                   f"e a autorização era da data original")
                reprovar(TIPO_AUTORIZACAO_VENCIDA,
                         f"autorização vencida: validade {val} é anterior ao atendimento {da}"
                         + complemento,
                         "obter autorização válida na data do atendimento e lançar o novo número")
        elif sinais.get("remarcada_de"):
            alertas.append(f"sessão remarcada de {sinais['remarcada_de']}: a validade "
                           f"({val}) cobre a data nova ({da}); nada a fazer")

    # --- 4) Sessão <= limite do convênio (FONTE = JSON, não a coluna do CSV). ---
    limite_json = regra.get("limite_sessoes_por_autorizacao")
    sessao = guia.get("sessao_numero_na_autorizacao")
    if limite_json is not None and sessao is not None and sessao > limite_json:
        reprovar(TIPO_SESSAO_ACIMA_LIMITE,
                 f"sessão {sessao} passa do limite de {limite_json} do {nome}",
                 "solicitar nova autorização/reavaliação antes de faturar esta sessão")
    limite_csv = guia.get("autorizacao_sessoes_limite")
    if limite_csv is not None and limite_json is not None and limite_csv != limite_json:
        alertas.append(f"limite de sessões digitado na guia ({limite_csv}) diverge do "
                       f"limite oficial do {nome} ({limite_json}); valeu o do convênio")

    # --- 5) Procedimento: existe, está na tabela, é coberto; e o sinal de código errado. ---
    proc = guia.get("procedimento_codigo")
    cobertos = regra.get("procedimentos_cobertos", [])
    na_tabela = _procedimento(regras, proc) is not None
    if not proc:
        reprovar(TIPO_CAMPO_OBRIGATORIO,
                 "campo obrigatório ausente: código do procedimento",
                 "preencher o código do procedimento antes do envio")
    elif not na_tabela:
        reprovar(TIPO_PROCEDIMENTO_FORA_TABELA,
                 f"código {proc} não está na tabela de procedimentos",
                 "conferir o código do procedimento no sistema (provável erro de digitação)")
    elif proc not in cobertos:
        reprovar(TIPO_NAO_COBERTO,
                 f"procedimento {proc} não é coberto pelo {nome}",
                 "não enviar ao convênio: faturar como particular")
    if sinais.get("codigo_errado"):
        # Sinal da IA: acrescenta motivo, nunca suprime a checagem de cobertura acima.
        real = sinais.get("procedimento_real") or "o procedimento realizado"
        reprovar(TIPO_CODIGO_ERRADO,
                 f"código lançado ({proc}) não corresponde ao procedimento realizado "
                 f"({real}), segundo a recepção",
                 f"lançar o código correto de {real} e conferir se o {nome} cobre; "
                 f"se não estiver na tabela, faturar como particular")

    # --- 6) Paciente pediu particular: sai do fluxo de convênio. ---
    if sinais.get("faturar_particular"):
        reprovar(TIPO_PARTICULAR,
                 "paciente pediu para faturar como particular, não quer usar o convênio",
                 "não enviar ao convênio: emitir como particular")

    # --- 7) Prazo de envio: dias que restam para a guia CHEGAR ao convênio. ---
    prazo = regra.get("prazo_envio_dias")
    if da and data_ref and prazo is not None:
        decorridos = _dias_entre(da, data_ref)
        if decorridos is not None:
            dias_para_prazo = prazo - decorridos
            if dias_para_prazo < 0:   # o último dia do prazo ainda vale
                reprovar(TIPO_PRAZO_ENVIO,
                         f"prazo de envio perdido: {decorridos} dias desde o atendimento "
                         f"(limite {prazo} do {nome})",
                         "enviar imediatamente e negociar com o convênio; prazo vencido "
                         "costuma ser recusado")
            elif dias_para_prazo <= DIAS_ALERTA_URGENTE:
                urgente = True
                alertas.append(f"URGENTE: restam {dias_para_prazo} dia(s) para o prazo de "
                               f"envio do {nome} ({prazo} dias do atendimento)")

    # --- 8) Valor lançado vs valor de referência do procedimento (alerta). ---
    ref = _procedimento(regras, proc)
    if ref and isinstance(valor, (int, float)) and abs(valor - ref["valor_referencia"]) > 0.005:
        alertas.append(f"valor lançado (R$ {valor:.2f}) diverge da referência do "
                       f"procedimento (R$ {ref['valor_referencia']:.2f})")

    # --- 9) Duplicata: a cópia (id maior) não vai; a original ganha alerta. ---
    if ids_duplicata:
        menor = min(ids_duplicata, key=_ordem_id) if guia_nova else min(ids_duplicata + [id_guia], key=_ordem_id)
        if guia_nova or menor != id_guia:
            reprovar(TIPO_DUPLICATA,
                     f"mesma carteirinha, autorização, data e procedimento de {menor}",
                     f"não enviar: conferir se é cobrança repetida e manter só {menor}")
        else:
            alertas.append(f"tem cópia com os mesmos dados: {', '.join(ids_duplicata)} "
                           f"(a cópia está marcada como NÃO ENVIAR)")

    # --- 10) Observação da recepção: sem IA, pede leitura; com IA, os sinais já agiram. ---
    obs = (guia.get("observacao_recepcao") or "").strip()
    if obs:
        if sinais.get("nao_lida"):
            reprovar(TIPO_OBSERVACAO_NAO_LIDA,
                     f"observação não lida pela IA (IA fora do ar no momento): \"{obs}\"",
                     "leitura humana da observação, ou conferir de novo quando a IA voltar")
        elif not sinais and not observacao_trivial(obs):
            reprovar(TIPO_OBSERVACAO,
                     f"observação da recepção requer leitura: \"{obs}\"",
                     "ler a observação e decidir a exceção")

    return _montar_decisao(id_guia, convenio, motivos, correcoes, alertas, tipos,
                           valor, urgente, dias_para_prazo)


def _montar_decisao(id_guia, convenio, motivos, correcoes, alertas, tipos,
                    valor, urgente, dias_para_prazo):
    """Fecha a Decisao aplicando a prioridade NÃO ENVIAR > CORRIGIR > OK."""
    v = float(valor) if isinstance(valor, (int, float)) else 0.0
    if any(t in TIPOS_NAO_ENVIAR for t in tipos):
        decisao = NAO_ENVIAR
        risco, reclass = 0.0, (0.0 if TIPO_DUPLICATA in tipos else v)
    elif motivos:
        decisao = CORRIGIR
        risco, reclass = v, 0.0
    else:
        decisao = OK
        risco, reclass = 0.0, 0.0
    return {
        "id_guia": id_guia,
        "convenio": convenio,
        "decisao": decisao,
        "motivos": motivos,
        "correcoes": correcoes,
        "alertas": alertas,
        "tipos": tipos,
        "valor": v,
        "valor_em_risco": risco,
        "valor_reclassificar": reclass,
        "urgente": urgente,
        "dias_para_prazo": dias_para_prazo,
    }
