# ARQUITETURA + PLANO DE BUILD — Prova 2 Expert Integrado ("Consultor de Negócios com IA")
Caso: Clínica Vitalis — conferência de guias ANTES do envio ao convênio + relatório de terça.
Autor do plano: Estrategista (Fable) · 2026-09-20 · Prazo da prova: 19/10 · Teto: ~6h "dela".

> Princípio que organiza tudo (e que é a voz da Chefe): **regra objetiva é código auditável;
> IA só entra onde há linguagem humana; e a IA nunca aprova sozinha — no máximo rebaixa
> para "pendente com recomendação"**. Humano no controle, mecanismo antes de hype.
> Fio narrativo com a prova 1: lá ela deixou a glosa para "uma segunda fase" — esta prova
> É a segunda fase. Abrir o README e o vídeo com essa frase.

---

## 1. ARQUITETURA DA SOLUÇÃO

```
                       ┌────────────────────────────────────────────┐
 guia nova (CSV/colada)│  1. NORMALIZADOR (determinístico)          │
 ─────────────────────▶│  datas BR→ISO · vírgula→ponto · trim/campos │
                       │  vazios · chave de duplicata               │
                       └───────────────┬────────────────────────────┘
                                       ▼
                       ┌────────────────────────────────────────────┐
                       │  2. MOTOR DE REGRAS (determinístico, puro) │
                       │  cruza guia × regras_convenio.json:        │
                       │  campos obrigatórios POR convênio · validade│
                       │  da autorização · sessão ≤ limite · proced. │
                       │  coberto · prazo de envio · duplicata      │
                       │  → lista de TODOS os motivos (não só o 1º) │
                       └───────────────┬────────────────────────────┘
                                       ▼
                       ┌────────────────────────────────────────────┐
                       │  3. CAMADA DE INTERPRETAÇÃO (IA — Claude)  │
                       │  SÓ para observacao_recepcao não trivial.  │
                       │  Pode: acrescentar pendência, recomendar   │
                       │  correção, apontar exceção prevista na     │
                       │  regra (ex.: verbal c/ protocolo, 5 dias). │
                       │  NÃO pode: transformar pendente em OK.     │
                       └───────────────┬────────────────────────────┘
                                       ▼
                  DECISÃO: OK | PENDENTE (+ motivos + correção sugerida + valor em risco)
```

**Consumidores do núcleo (mesmo verificador, 3 portas):**
- **Batch** `verificar_lote.py` roda as 80 guias → `resultados.csv/json` + **relatório de
  terça** (`relatorio-terca.md` + versão HTML) — contagens, tipos de problema, R$ em risco,
  corte por unidade e por convênio.
- **MCP server** (`mcp_guias/`) expõe o núcleo como tools (seção MCP abaixo).
- **Skill** `verificar-guia`: a operadora COLA a guia como a recepção escreveu; a Skill
  estrutura os campos e chama o MCP; devolve OK/pendente + motivo + o que corrigir.

**Onde a IA entra / onde NÃO entra (decisão central, auditável):**
- NÃO entra: passos 1 e 2. Data vencida é data vencida — comparação de datas em código, com
  teste. Isso é o que torna a decisão explicável na entrevista e barata de rodar.
- ENTRA: passo 3, apenas nas ~5-6 guias com texto livre que muda o quadro:
  - G-2608-0030: autorização vencida MAS "trouxe autorização nova, validade 30/09" → segue
    PENDENTE (motivo: lançar o número novo antes do envio) com recomendação clara.
  - G-2608-0041: Saúde Interior sem nº de autorização MAS "autorizado por telefone,
    protocolo 771203" → a regra do convênio ACEITA verbal com protocolo por 5 dias úteis; a
    IA aponta a exceção e o prazo-limite para lançar o número. Continua PENDENTE até lançar.
  - G-2608-0034: sessão remarcada, "autorização era da data original" → conferir validade
    contra a data nova; alerta.
  - G-2608-0039: paciente "quer faturar como particular" → guia sai do fluxo de convênio
    (política: marcar NÃO-ENVIAR-CONVÊNIO, pendente de reclassificação).
  - G-2608-0069: "procedimento realizado foi drenagem linfática, lançar o código certo" →
    código lançado não corresponde ao realizado; PENDENTE crítico (risco de glosa e de
    inconsistência de prontuário).
- **Degradação segura:** se a IA estiver indisponível, o passo 3 marca "observação da
  recepção requer revisão humana" e a guia fica PENDENTE. O sistema nunca quebra nem
  aprova às cegas por falta de IA (critério "erro tratado" da prova).

**Decisões com 3 informações sempre juntas:** veredito + motivo(s) em português claro +
correção sugerida. É o que a recepção precisa para agir ANTES do envio — o objetivo real
da clínica (glosa evitada, não glosa relatada).

**Fonte de verdade:** `regras_convenio.json` (nunca hardcode de regra no código) e
`guias.csv` lidos direto do disco. Sem banco: 900 guias/mês não justificam; menos peça
móvel = mais explicável. (A coluna `autorizacao_sessoes_limite` do CSV é IGNORADA como
fonte — vale o JSON do convênio; divergência vira alerta. Ver Decisão 3.)

**Publicação (custo zero, sem segredo):**
- Repo PÚBLICO no GitHub **da conta dela** com tudo: código, MCP, Skill, prompts, README.
- "Link rodando com as 80 guias" = **GitHub Pages** servindo o relatório HTML gerado pelo
  batch: as 80 guias com veredito/motivo (filtro por tipo/unidade em JS puro) + o relatório
  de terça do Dr. Renato. Estático = custo zero, nada pra cair, nenhuma chave.
- A parte "viva" (Skill + MCP) roda no Claude da conta dela — o avaliador instala pelo
  README (2 comandos) e testa com guia nova. Nenhuma API key no projeto: a IA da solução É
  o Claude que hospeda a Skill (ver Decisão 4).
- Guarda anti-segredo: `.gitignore` + varredura gitleaks antes de todo push (linha vermelha).

---

## 2. RECOMENDAÇÃO DE STACK (escolha final é dela — gate 0)

| Peça | Recomendação | Por quê (trade-off) |
|---|---|---|
| Linguagem | **Python 3, stdlib** (csv, json, datetime, unittest) | Zero dependência no núcleo = instala em qualquer máquina, fácil de explicar linha a linha. Alternativa Node: nada ganha aqui. |
| Motor de regras | Funções puras `verificar(guia, regras) -> Decisao` | Testável, determinístico, auditável. Sem engine de regras externa (overkill, inexplicável). |
| MCP | **SDK oficial `mcp` (FastMCP), transporte stdio** | Padrão de mercado, instalação = 1 bloco no `claude_desktop_config.json`/`.mcp.json`. Única dependência pip do projeto. |
| Skill | Skill do Claude (`SKILL.md` + instruções) no repo | Exigência literal da prova; roda na conta dela, custo zero. |
| IA (passo 3) | **Claude da conta dela via Skill/MCP** (sem chamada de API no código batch) | Sem chave no repo, custo zero pra Expert. Batch tem modo `--sem-ia` que degrada para "revisão humana". |
| Hospedagem do link | **GitHub Pages** (HTML estático gerado pelo batch) | Custo zero, sem servidor, sem env vars. Alternativas (Render/Railway free) = mais pontos de falha e config, sem ganho pro avaliador. |
| Vídeo | Gravação de tela (OBS/Loom free), ≤5min | Ela narrando > produção. |

Defesa em uma frase (para a entrevista): "escolhi a pilha mais simples que resolve —
Python puro auditável para regra, MCP padrão para expor, Claude para linguagem humana,
estático para publicar. Cada peça a mais seria uma peça que eu teria que defender."

---

## 3. AS DECISÕES DELA (README "o que a IA gerou × o que eu mudei/decidi na mão")

⚠️ Para serem verdadeiras, essas decisões são apresentadas à Chefe no GATE 0 como
PERGUNTAS ABERTAS com recomendação — ela bate o martelo (e pode divergir). O que ela
decidir é o que vai pro README, com as palavras dela.

1. **Determinístico separado de IA.** "Regra de convênio é código com teste, não prompt.
   IA só interpreta o que a recepção escreveu em texto livre — e mesmo aí ela não aprova:
   no máximo explica e recomenda. Quem aprova exceção é gente." (Recomendada: é a espinha
   da solução e o critério nº1 do avaliador — decisões que batem com os erros reais.)
2. **Duplicata nunca some em silêncio.** As duas guias repetidas (0027/0057, 0059/0076)
   viram PENDENTE "possível duplicata" apontando o par — nunca descarte automático.
   Cobrança duplicada em convênio é risco maior que glosa.
3. **Fonte de verdade é a regra do convênio, não o que a recepção digitou.** O limite de
   sessões digitado na guia é ignorado para o veredito (a recepção digita errado — é a
   causa raiz do caso); vale o `regras_convenio.json`. Divergência entre os dois vira
   alerta próprio.
4. **Nenhuma chave no projeto.** A IA da solução é o Claude onde a Skill roda (conta dela);
   o pipeline batch funciona 100% sem rede. Repo público sem um segredo sequer, por
   construção e por varredura antes do push.
5. **Três informações por decisão, sempre.** Veredito + motivo em português de recepção +
   correção sugerida. "Reprovado" sem 'o que fazer' não evita glosa nenhuma.
6. **Data de referência do lote é parâmetro explícito** (para prazo de envio): o batch das
   80 roda com data fixa documentada (ex.: 2026-09-01) para o resultado ser reprodutível
   pelo avaliador; em produção seria a data do dia.

(O README lista também **o que ficou de fora e por quê**: integração com a API do sistema
de gestão, alerta no ato do lançamento, dashboard — "fase 2 real do cliente; a prova pede o
verificador funcionando e explicável, não a integração". Coerente com o faseamento dela.)

---

## 4. PLANO DE BUILD EM FASES (nós construímos; ela decide, entende e assina)

| Fase | O quê | Quem | Esforço agente | Tempo DELA | Gate da Chefe |
|---|---|---|---|---|---|
| **F0** | Perguntas de decisão (seção 6) + decisões 1-6 para ela bater martelo | Maya | 15min | **20min** | GATE 0: decisões registradas nas palavras dela |
| **F1** | Normalizador + motor de regras + testes (as ~40 guias-problema como casos de teste) + batch → resultados 80 + relatório de terça v1 (md+html) | paulo-dev | ~2h | **45min** | GATE 1: ela revisa 10 guias-amostra (1 de cada tipo) e o relatório; critério = ela explica CADA veredito sem olhar o código |
| **F2** | MCP server (tools abaixo) + Skill `verificar-guia` + instalação documentada e testada em ambiente limpo | paulo-dev | ~2h | **30min** | GATE 2: ela instala na conta DELA e roda 3 guias coladas (1 OK, 1 vencida, 1 texto livre 0041) |
| **F3** | Repo público na conta dela + Pages + README "Como fiz" (rascunho jonathan-copy na voz dela com input do Paulo; ELA edita — a edição dela é real e vira evidência) + varredura de segredo | paulo-dev + jonathan-copy | ~1.5h | **40min** | GATE 3: ela aprova README linha a linha (é o texto que ela defende) |
| **F4** | Roteiro do vídeo ≤5min (jonathan) + estrutura de gravação (breno orienta; ELA grava e narra) | jonathan-copy + breno-video | ~1h | **60min** | GATE 4: vídeo dela aprovado por ela |
| **F5** | QA adversarial final: 5 guias novas inventadas (convênio inexistente, data lixo, campos faltando, duplicata nova, texto livre novo) contra o link e o MCP + checklist dos 8 campos da prova | Fable (validação) + verificador isolado | ~45min | **15min** | Entrega: checklist ✅/❌ com evidência |
| **F6** | Preparo de entrevista (seção 5) | Maya + jonathan | ~45min | **60-90min** | Simulação de perguntas com ela |

Tempo total dela: **~4h30-5h** — dentro do teto de ~6h e é o número honesto para o README.
Dependências: F0→F1→F2→F3→(F4∥F5)→F6. prometo.sh por fase; Juliana coordena F1-F5
(composta, 4 agentes).

**Tools do MCP (F2):**
1. `consultar_regra(convenio, procedimento_codigo)` → campos obrigatórios, cobertura,
   validade máx., limite de sessões, prazo de envio, observação (a exceção verbal do Saúde
   Interior sai daqui).
2. `verificar_guia(campos da guia)` → `{decisao, motivos[], correcoes[], valor_em_risco}` —
   erro de input (campo faltando, data inválida, convênio desconhecido) responde
   estruturado, nunca stack trace.
3. (barata e vistosa) `resumo_lote()` → os números do relatório de terça a partir do
   `resultados.json`. Cobre "pelo menos 2" com folga.

**Relatório de terça (conteúdo fixo):** conferidas (80) · OK · pendentes por TIPO
(vencida 13, campo obrigatório 8, sessão acima do limite 6, não coberto 5, texto livre 5,
formato 3, duplicata 2 pares — números finais saem do motor, não desta estimativa) ·
**R$ em risco** (soma do valor das pendentes) · corte por unidade e convênio · top 3 ações
da semana. Uma página, linguagem de dono de clínica, número antes de adjetivo.

---

## 5. ESTRATÉGIA DE ENTREVISTA ("ela sabe o que construiu")

O critério decisivo da prova é este. Preparação em 3 peças (F6):
1. **Mapa guia-a-guia** (1 doc interno): cada guia reprovada → regra exata que pegou →
   linha do JSON que a justifica. Ela estuda os 7 tipos, não 40 casos decorados. Os 5 de
   texto livre ela conta como HISTÓRIA (são os melhores momentos: "a 0041 estava sem
   número, mas a recepção anotou o protocolo — e a regra do Saúde Interior aceita verbal
   por 5 dias úteis; o sistema aponta a exceção e cobra o número antes do envio").
2. **As 6 decisões em 1 frase cada** (as da seção 3, nas palavras dela) + a defesa de
   stack em 1 frase. Perguntas prováveis ensaiadas: "por que não deixou o LLM decidir
   tudo?", "e se chegar um convênio novo?" (resposta: adicionar bloco no JSON, zero
   código), "e se a guia vier num formato quebrado?" (normalizador + erro tratado,
   demonstrável ao vivo), "como sabe que está certo?" (testes com as 40 guias-problema
   como gabarito).
3. **Demo de 90 segundos ensaiada:** colar uma guia nova na Skill ao vivo → decisão +
   motivo + correção. É a prova prática de "aguenta guia nova".
Regra de ouro do ensaio: se ela precisar de nós para responder alguma pergunta da
simulação, aquele ponto volta pro gate — a entrega só fecha quando ela responde tudo só.

## 6. RISCOS + PERGUNTAS PARA A CHEFE (antes do build — decisões DELA)

**Perguntas (gate 0, respostas fechadas):**
1. Conta GitHub e NOME do repo (sugestão: `vitalis-conferencia-guias`). O repo nasce na
   conta DELA (exigência de infra dela; nós preparamos, ela cria/pusha ou nos dá acesso
   temporário — como prefere?).
2. GitHub Pages como "link publicado" está OK, ou prefere outro host dela?
3. Topa gravar o vídeo com a voz/tela dela? (Recomendado forte: o avaliador quer VER que
   ela domina. Nós entregamos roteiro e demo prontos.)
4. As 6 decisões da seção 3: valida/ajusta cada uma nas palavras dela.
5. Reunião de terça é 7h30: o relatório leva marca/tom "GEAIA aplicada" ou neutro-clínica?

**Riscos reais:**
- **R1 — Ela não conseguir defender algo na entrevista.** Mitigação: gates 1/2/3 têm
  critério explícito de ENTENDIMENTO (não só aprovação) + F6 com simulação e regra de ouro.
- **R2 — Segredo vazar no repo público.** Mitigação: por construção não há chave; ainda
  assim gitleaks antes de todo push + revisão de diff (linha vermelha 5 do SOUL).
- **R3 — "Nasceu pra prova"**: nenhum reuso de código EAIA existente; projeto escrito do
  zero neste diretório; histórico do repo começa limpo e datado. README diz com honestidade
  que ela operou a IA dela para construir — usar IA é esperado e é o diferencial dela,
  desde que as decisões sejam dela (gate 0 garante).
- **R4 — Avaliador não conseguir instalar o MCP.** Mitigação: F2 inclui teste de instalação
  em ambiente limpo (venv novo) seguindo SÓ o README.
- **R5 — Overengineering.** Teto: sem banco, sem framework web, sem dashboard dinâmico.
  "Não precisa ser bonito, precisa funcionar e ser explicável" é critério de corte em todo
  gate de QA.
- **R6 — Ambiguidade do prazo de envio** (qual "hoje"?). Resolvida pela Decisão 6 (data de
  referência parametrizada e documentada).

**Critérios de pronto da entrega (checklist F5 — os 8 campos da prova):**
☐ link Pages no ar com as 80 + relatório de terça ☐ descrição "guia entra → decisão sai"
no README ☐ MCP com ≥2 tools + instalação testada ☐ Skill funcionando com guia colada
☐ README com 3+ decisões dela, o que ficou de fora, como testou, quanto tempo ☐ vídeo ≤5min
☐ repo público sem segredo (gitleaks limpo) ☐ 5 guias novas adversariais sem quebrar.
