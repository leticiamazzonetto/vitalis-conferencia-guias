"""
observacao.py — Camada 3: a IA lê o texto livre da recepção e devolve SINAIS.

A IA NÃO decide. Ela transforma "Paciente trouxe autorização nova, validade 30/09" em
{"autorizacao_nova": true, "validade_nova": "2026-09-30", ...}. Quem decide com esses
sinais é o motor (motor.py), em código auditável.

Desenho (decisões do projeto):
  - Modelo pequeno e barato (claude-haiku-4-5), temperatura 0: a mesma frase gera sempre
    a mesma resposta. Custo: centavos pelas 80 guias; ~R$ 2/mês em 900 guias.
  - Saída em JSON com chaves fixas (prompts/observacao.md). Chave desconhecida é
    descartada; chave faltando recebe o valor padrão.
  - Cache por hash do texto: observações repetidas custam UMA chamada.
  - Falha (sem chave, sem rede, resposta ilegível) NUNCA derruba a verificação: devolve
    sinais com nao_lida=True e o motor marca CORRIGIR "observação não lida".
  - A chave da API vem da variável de ambiente ANTHROPIC_API_KEY. Nunca do código.
"""

import hashlib
import json
import os
import re

MODELO = "claude-haiku-4-5"
BASE = os.path.dirname(os.path.abspath(__file__))
CAMINHO_PROMPT = os.path.join(BASE, "prompts", "observacao.md")
CAMINHO_CACHE_PADRAO = os.path.join(BASE, "dados_app", "sinais_cache.json")

SINAIS_PADRAO = {
    "autorizacao_nova": False,
    "validade_nova": None,
    "numero_pendente": False,
    "protocolo_verbal": None,
    "faturar_particular": False,
    "codigo_errado": False,
    "procedimento_real": None,
    "remarcada_de": None,
    "irrelevante": False,
    "nao_lida": False,
}


def sinais_vazios():
    return dict(SINAIS_PADRAO)


def sinais_nao_lida(motivo=""):
    s = sinais_vazios()
    s["nao_lida"] = True
    s["_motivo"] = motivo
    return s


def _carregar_prompt():
    with open(CAMINHO_PROMPT, encoding="utf-8") as f:
        return f.read()


def _hash(texto, ano):
    return hashlib.sha256(f"{ano}|{texto.strip().lower()}".encode("utf-8")).hexdigest()


def _normalizar_sinais(bruto):
    """Garante as chaves fixas e os tipos; descarta o que a IA inventar a mais."""
    s = sinais_vazios()
    if not isinstance(bruto, dict):
        return sinais_nao_lida("resposta não é um objeto JSON")
    for k in SINAIS_PADRAO:
        if k == "nao_lida":
            continue
        if k in bruto:
            v = bruto[k]
            if isinstance(SINAIS_PADRAO[k], bool):
                s[k] = bool(v)
            else:
                s[k] = str(v).strip() if v not in (None, "", False) else None
    for k in ("validade_nova", "remarcada_de"):
        if s[k] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s[k]):
            s[k] = None  # data fora do formato: melhor sem sinal do que sinal errado
    return s


def _extrair_json(texto):
    """Pega o primeiro objeto JSON da resposta, mesmo se vier com texto em volta."""
    m = re.search(r"\{.*\}", texto, flags=re.S)
    if not m:
        raise ValueError("sem JSON na resposta")
    return json.loads(m.group(0))


class Cache:
    """Cache simples em arquivo JSON. Falha de disco nunca quebra a extração."""

    def __init__(self, caminho=CAMINHO_CACHE_PADRAO):
        self.caminho = caminho
        self.dados = {}
        try:
            with open(caminho, encoding="utf-8") as f:
                self.dados = json.load(f)
        except (OSError, ValueError):
            self.dados = {}

    def get(self, chave):
        return self.dados.get(chave)

    def put(self, chave, valor):
        self.dados[chave] = valor
        try:
            os.makedirs(os.path.dirname(self.caminho), exist_ok=True)
            with open(self.caminho, "w", encoding="utf-8") as f:
                json.dump(self.dados, f, ensure_ascii=False, indent=1)
        except OSError:
            pass


def _chamar_modelo(prompt_sistema, texto, ano):
    """Uma chamada ao Claude. Isolada para os testes trocarem por um dublê."""
    import anthropic  # importado aqui: o núcleo roda sem a biblioteca instalada
    cliente = anthropic.Anthropic(timeout=15.0, max_retries=1)
    resposta = cliente.messages.create(
        model=MODELO,
        max_tokens=300,
        # SDK 1.x tirou `temperature` da assinatura; a API do Haiku 4.5 ainda aceita.
        # Temperatura 0 = mesma frase, mesma resposta.
        extra_body={"temperature": 0},
        system=prompt_sistema,
        messages=[{"role": "user", "content":
                   f"Ano da guia: {ano}.\nObservação da recepção: \"{texto}\""}],
    )
    return "".join(b.text for b in resposta.content if b.type == "text")


def ia_disponivel():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def extrair_sinais(texto, ano=2026, cache=None, chamar=_chamar_modelo):
    """
    Devolve o dict de sinais para uma observação. Nunca levanta exceção.

      texto  : observação da recepção (string; vazia devolve sinais padrão)
      ano    : ano da guia, para completar datas "30/09"
      cache  : instância de Cache (None = cache padrão em dados_app/)
      chamar : função (prompt, texto, ano) -> string JSON. Trocável nos testes.
    """
    texto = (texto or "").strip()
    if not texto:
        s = sinais_vazios()
        s["irrelevante"] = True
        return s

    cache = cache or Cache()
    chave = _hash(texto, ano)
    em_cache = cache.get(chave)
    if em_cache:
        return _normalizar_sinais(em_cache)

    if chamar is _chamar_modelo and not ia_disponivel():
        return sinais_nao_lida("ANTHROPIC_API_KEY não configurada")

    try:
        bruto = chamar(_carregar_prompt(), texto, ano)
        sinais = _normalizar_sinais(_extrair_json(bruto))
    except Exception as exc:  # noqa: BLE001 — qualquer falha vira "não lida"
        return sinais_nao_lida(f"{type(exc).__name__}: {exc}")

    if not sinais.get("nao_lida"):
        cache.put(chave, sinais)
    return sinais
