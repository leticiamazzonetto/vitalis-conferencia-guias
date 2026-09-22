"""
normalizador.py — Camada 1 (determinística) do verificador de guias da Clínica Vitalis.

Objetivo: pegar a guia como a recepção digitou (com sujeira de digitação) e devolver
um registro LIMPO e previsível para o motor de regras conferir. Aqui NÃO há decisão de
convênio — só arrumação de formato:
  - datas em formato brasileiro (dd/mm/aaaa) viram ISO (aaaa-mm-dd);
  - valor com vírgula ("62,00") vira número (62.0);
  - todo campo de texto é aparado (trim) de espaços nas pontas;
  - números (sessão, limite) viram inteiro quando dá;
  - uma "chave de duplicata" é montada para o motor detectar guia repetida.

Regra de ouro: NUNCA levanta exceção para o chamador. Entrada com lixo (data inválida,
valor sem número) é tratada — o campo problemático fica marcado em `_erros`, e a guia
segue para o motor, que a devolve como PENDENTE. O sistema nunca quebra por causa de um
dado torto (critério "erro tratado" da prova).

Escrito em Python 3, só biblioteca padrão. Zero dependência externa.
"""

from datetime import date

# Colunas de data que a recepção preenche. São as únicas que passam pela conversão BR->ISO.
CAMPOS_DATA = ("data_atendimento", "autorizacao_validade", "data_lancamento")

# Colunas numéricas inteiras.
CAMPOS_INTEIROS = ("autorizacao_sessoes_limite", "sessao_numero_na_autorizacao")


def normalizar_texto(valor):
    """Aparita espaços nas pontas. None vira string vazia. Nunca falha."""
    if valor is None:
        return ""
    return str(valor).strip()


def normalizar_data(valor):
    """
    Converte uma data para o formato ISO 'aaaa-mm-dd'.

    Aceita:
      - 'aaaa-mm-dd'  (já ISO)          -> devolve igual
      - 'dd/mm/aaaa'  (formato BR)      -> converte para ISO
      - ''  ou None   (campo vazio)     -> ('', False, None)   (vazio não é erro aqui;
                                            a obrigatoriedade é checada pelo motor)

    Retorna uma tupla (iso, foi_convertida, erro):
      - iso: a data em ISO, ou o valor original se não deu para entender
      - foi_convertida: True se veio em BR e foi convertida (para registrar a normalização)
      - erro: mensagem se a data era inválida, senão None
    """
    texto = normalizar_texto(valor)
    if texto == "":
        return "", False, None

    # Já está em ISO? Validamos que é uma data real (ex.: rejeita 2026-13-40).
    if "-" in texto and "/" not in texto:
        try:
            date.fromisoformat(texto)
            return texto, False, None
        except ValueError:
            return texto, False, f"data inválida: {texto!r}"

    # Formato brasileiro dd/mm/aaaa.
    if "/" in texto:
        partes = texto.split("/")
        if len(partes) == 3:
            dia, mes, ano = partes
            try:
                iso = date(int(ano), int(mes), int(dia)).isoformat()
                return iso, True, None
            except (ValueError, TypeError):
                return texto, False, f"data inválida: {texto!r}"
        return texto, False, f"data inválida: {texto!r}"

    return texto, False, f"data inválida: {texto!r}"


def normalizar_valor(valor):
    """
    Converte o valor monetário para float.
      - '62,00' (vírgula BR) -> 62.0
      - '62.00' (ponto)      -> 62.0
      - '1.234,56'           -> 1234.56  (ponto de milhar + vírgula decimal)
      - '' ou None           -> (None, False, None)

    Retorna (numero, foi_convertida_de_virgula, erro).
    'foi_convertida_de_virgula' marca quando a vírgula BR precisou ser trocada por ponto,
    para registrarmos a normalização de formato.
    """
    texto = normalizar_texto(valor)
    if texto == "":
        return None, False, None

    tinha_virgula = "," in texto
    limpo = texto
    if "," in limpo:
        # Padrão BR: ponto é separador de milhar, vírgula é decimal.
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return float(limpo), tinha_virgula, None
    except ValueError:
        return None, False, f"valor inválido: {texto!r}"


def normalizar_inteiro(valor):
    """Converte para int. Vazio -> (None, None). Lixo -> (None, erro)."""
    texto = normalizar_texto(valor)
    if texto == "":
        return None, None
    try:
        return int(texto), None
    except ValueError:
        return None, f"número inválido: {texto!r}"


def chave_valida(chave):
    """A chave só identifica alguém com carteirinha E data de atendimento preenchidas."""
    return bool(chave) and len(chave) >= 3 and bool(chave[0]) and bool(chave[2])


def chave_duplicata(guia):
    """
    Monta a chave que identifica uma guia repetida:
    carteirinha + número da autorização + data do atendimento + código do procedimento.
    Duas guias com a MESMA chave são candidatas a duplicata (mesmo paciente, mesma
    autorização, mesmo dia, mesmo procedimento) — o motor as marca como PENDENTE, nunca
    descarta em silêncio (Decisão 2 do projeto).
    """
    return (
        normalizar_texto(guia.get("carteirinha")),
        normalizar_texto(guia.get("numero_autorizacao")),
        normalizar_texto(guia.get("data_atendimento")),
        normalizar_texto(guia.get("procedimento_codigo")),
    )


def normalizar_guia(bruta):
    """
    Recebe a guia crua (dict, como sai do csv.DictReader ou colada pela recepção) e
    devolve um dict normalizado, pronto para o motor. NUNCA levanta exceção.

    Campos extras adicionados ao dict de saída:
      _notas  : lista de normalizações de formato aplicadas (ex.: data BR convertida)
      _erros  : lista de problemas de dado que impedem conferência confiável
      _chave_dup : a chave de duplicata (tupla)

    A chave de duplicata é montada DEPOIS de normalizar a data, para que 26/08/2026 e
    2026-08-26 gerem a mesma chave.
    """
    if not isinstance(bruta, dict):
        # Entrada completamente fora do formato: devolve registro mínimo marcado com erro.
        return {"_notas": [], "_erros": ["registro não é um conjunto de campos válido"], "_chave_dup": ()}

    g = {}
    notas = []
    erros = []

    # 1) Aparar todos os campos de texto.
    for chave, valor in bruta.items():
        g[chave] = normalizar_texto(valor)

    # 2) Datas BR -> ISO.
    for campo in CAMPOS_DATA:
        iso, convertida, erro = normalizar_data(g.get(campo, ""))
        g[campo] = iso
        if convertida:
            notas.append(f"{campo}: formato BR convertido para ISO ({iso})")
        if erro:
            erros.append(erro)

    # 3) Valor monetário (vírgula -> ponto).
    numero, virgula, erro = normalizar_valor(g.get("valor", ""))
    g["valor"] = numero
    if virgula:
        notas.append("valor: vírgula decimal convertida para ponto")
    if erro:
        erros.append(erro)

    # 4) Campos inteiros.
    for campo in CAMPOS_INTEIROS:
        inteiro, erro = normalizar_inteiro(g.get(campo, ""))
        g[campo] = inteiro
        if erro:
            erros.append(f"{campo}: {erro}")

    # 5) Chave de duplicata (usa a data já em ISO).
    g["_notas"] = notas
    g["_erros"] = erros
    g["_chave_dup"] = chave_duplicata(g)

    return g
