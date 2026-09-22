# Vitalis · Conferência de guias antes do envio ao convênio

> Prova técnica (2ª fase) do processo seletivo da Expert Integrado para Consultor de Negócios com IA.
> Na primeira prova eu deixei a glosa para "uma segunda fase". Esta é a segunda fase.
> **Dados fictícios fornecidos pela banca.** Nenhum paciente, profissional ou convênio é real.

**Link rodando:** https://vitalis.geaia.com
**MCP publicado:** https://vitalis.geaia.com/mcp

A Clínica Vitalis lança cerca de 900 guias de convênio por mês e só descobre o erro quando o convênio glosa, 60 dias depois. Esta ferramenta confere cada guia **antes** do envio e diz, em português de recepção, o que está errado e o que fazer. O dono vê toda semana quantas guias foram conferidas, quantas têm problema, de que tipo e quanto dinheiro está em jogo.

## Como a guia entra e a decisão sai

```
guia (formulário, texto colado, CSV, ou chamada ao MCP)
  → normalizador.py   arruma o formato: data dd/mm → ISO, "62,00" → 62.0, campos vazios
  → observacao.py     a IA lê o que a recepção escreveu à mão e marca caixinhas (sinais)
  → motor.py          a REGRA decide, comparando a guia com regras_convenio.json
  → decisão: OK | CORRIGIR | NÃO ENVIAR + por quê + o que fazer + valor
```

Três estados, nomeados pela ação da clínica:

| Estado | Significa | Exemplo real do lote |
|---|---|---|
| **OK** | Pode ir ao convênio | G-2608-0001 |
| **CORRIGIR** | Falta algo que a recepção resolve no sistema de gestão antes do envio | G-2608-0041: autorização verbal, lançar o número até 27/08 |
| **NÃO ENVIAR** | O convênio não cobre (faturar particular), o paciente pediu particular, ou é cópia de outra guia (descartar) | G-2608-0002: consulta no Plano Bem |

A correção acontece **no sistema de gestão** (que não vai ser trocado). A ferramenta não guarda a guia, guarda a decisão sobre ela. Depois de corrigir, a guia é conferida de novo e vira OK.

## O que o site mostra (https://vitalis.geaia.com)

- **Painel**: cartões (conferidas, OK, corrigir, não enviar, prazo de envio), tabela com filtros por unidade, convênio, profissional, procedimento, decisão, tipo de problema e busca por guia ou paciente; detalhe de cada guia com "por quê" e "o que fazer".
- **Lista de correções**: o que cada unidade precisa fazer hoje, guia por guia, com filtros e download em CSV.
- **Conferir guia**: formulário, texto colado como a recepção escreve, ou CSV. A guia nova é comparada com o lote e com o histórico (cópia) e fica gravada em SQLite.
- **Relatório semanal**: o quadro da semana, decisões, problemas por tipo, por unidade e por convênio, com filtro por semana; cada ação do "Top 3" abre a lista de correções já filtrada.
- **Regras dos convênios**: o que cada convênio exige e cobre, direto do arquivo de regras.

## Números do lote de agosto (80 guias, IA ligada)

| | Guias | Valor |
|---|---:|---:|
| OK | 46 | R$ 3.162,00 |
| CORRIGIR | 26 | R$ 1.760,00 recuperáveis se corrigidas |
| NÃO ENVIAR | 8 | R$ 612,00 a faturar como particular (cópias valem 0) |

Problemas por tipo: 12 autorização vencida · 7 campo obrigatório faltando · 6 sessão acima do limite · 5 procedimento não coberto · 2 cópia de outra guia · 1 autorização nova a lançar · 1 autorização verbal a regularizar · 1 código do procedimento errado · 1 paciente optou por particular.

Relatório gerado pela ferramenta: `docs/relatorio-terca.md` (e a página "Relatório semanal" do site).

## MCP

`mcp_server/server.py` expõe as duas funções de `servico.py` como ferramentas, sem regra própria:

| Ferramenta | O que faz |
|---|---|
| `consultar_regra(convenio, procedimento_codigo)` | o que o convênio exige e cobre, limite de sessões, prazo de envio, observação do convênio |
| `verificar_guia(guia)` | decisão + motivos + correções + valores para uma guia como a recepção lançou |
| `resumo_lote()` | os números do lote de agosto |

**Instalar (local, stdio):**
```bash
pip install -r requirements.txt
# no Claude Code: abra a pasta do repositório; o .mcp.json já registra o servidor. Ou:
claude mcp add vitalis-guias -- python mcp_server/server.py
```
Claude Desktop (`claude_desktop_config.json`):
```json
{ "mcpServers": { "vitalis-guias": { "command": "python", "args": ["CAMINHO/mcp_server/server.py"] } } }
```
**Usar sem instalar (HTTP):** `https://vitalis.geaia.com/mcp` (transporte streamable HTTP; o mesmo servidor, rodando na VPS atrás do Caddy).

Teste de ponta a ponta: `python -m unittest tests.test_mcp` sobe o servidor por stdio e chama as três ferramentas.

## Skill

`.claude/skills/conferir-guia/SKILL.md`: a recepcionista cola a guia do jeito que saiu da tela ("SI, carteirinha 555123456, sessão musculoesquelética, atend 28/08, obs: autorizado por telefone, protocolo 990421"), a Skill monta os campos, chama `verificar_guia` no MCP e responde no formato fixo: selo, por quê, fazer. No Claude Code a Skill é descoberta ao abrir o repositório.

## Como fiz

### Ferramentas e por quê

| Peça | Escolha | Por quê |
|---|---|---|
| Linguagem | Python 3, biblioteca padrão no núcleo | Uma regra é uma linha legível. Sem framework para explicar. |
| Regras | `regras_convenio.json` é a fonte de verdade | Convênio novo = bloco novo no JSON, zero código. O limite de sessões digitado na guia só gera alerta se divergir. |
| IA | Claude Haiku 4.5 via API, só na observação da recepção | Custa centavos (9 chamadas para 80 guias, com cache por texto). A IA marca caixinhas; a regra decide. Se a IA cair, a guia vai para leitura humana. |
| Site | Streamlit | Um arquivo, lido de cima para baixo. |
| Histórico | SQLite em arquivo | 900 guias/mês não pedem banco gerenciado. Trocar por Postgres é uma classe (`app/armazenamento.py`). |
| Hospedagem | Meu servidor (VPS) com Caddy e systemd | Plano grátis dorme e apaga o histórico; a banca abre o link semanas depois. A chave da IA fica em `/etc/vitalis/env`, fora do repositório. |
| MCP | SDK oficial `mcp` (2.x), stdio + HTTP | Mesma função do site. Publicado por HTTP para testar sem instalar. |
| Testes | `unittest` + gabarito independente | 78 testes: uma regra por teste, 5 casos reais de texto livre com dublê da IA, MCP de ponta a ponta, e o lote inteiro contra um gabarito gerado por uma implementação que **não** importa o motor. |

### O que a IA gerou e o que eu mudei na mão

A IA gerou a maior parte do código. As decisões abaixo são minhas, e mudaram o que a IA tinha proposto:

1. **Três estados, não dois.** A primeira versão tinha só OK e PENDENTE, e somava como "recuperável" R$ 550 de procedimentos que o convênio nunca vai pagar e R$ 160 de cópias. "Não enviar" é nomeado pela ação da clínica: faturar particular ou descartar. Não chamei de "recusar", porque isso seria prever o convênio sem fonte.
2. **A IA não decide.** Ela só transforma o bilhete da recepção em sinais (`autorizacao_nova`, `protocolo_verbal`, `faturar_particular`...). Quem decide é `motor.py`, com teste. Temperatura zero, JSON fechado, cache, e falha vira "observação não lida" em vez de erro.
3. **Prazo de envio contado do atendimento até a data da conferência.** A fórmula original (lançamento − atendimento) nunca disparava. Depois da orientação da banca, o lote de agosto é conferido na data de lançamento de cada guia; guia nova é conferida hoje.
4. **Cópia de guia: uma vale, a outra não.** A original ganha aviso; a cópia vira NÃO ENVIAR com valor zero. Antes contava R$ 160 de risco que não existia.
5. **Gabarito escrito fora do motor.** O teste das 80 guias compara o motor com `tests/gabarito.csv`, gerado por `tests/gerar_gabarito.py`, que reescreve as regras do zero sem importar o motor. Se os dois discordarem, o teste acusa.
6. **Hospedar no meu servidor.** Streamlit Community Cloud dorme após 12 horas sem tráfego e o histórico some; Vercel + Supabase eram nove peças para explicar. Um subdomínio no Caddy que já servia meus sites resolveu com quatro peças.

### O que ficou de fora e por quê

- **Validade máxima da autorização (30/45/60 dias)**: o CSV não tem a data de concessão. Perguntei à banca; a resposta foi que a verificação possível é validade contra a data do atendimento. Fica documentado, não implementado.
- **Integração com a API do sistema de gestão**: não existe nesta prova. O MCP é a porta onde ela encaixaria.
- **Botão "marcar como corrigida"**: se o sistema de gestão tem API, quem sabe se a guia foi corrigida é ele, não um botão nosso. A guia corrigida é reconferida e vira OK.
- **Feriados** no cálculo de dias úteis da autorização verbal.
- **Inferência entre guias** (contar sessões de um paciente ao longo do mês): a banca orientou "confere o que a guia declara".

### Como testei

```bash
python -m unittest discover -s tests     # 78 testes: regras, sinais da IA (dublê), gabarito das 80, MCP stdio
python verificar_lote.py [--com-ia]      # lote de agosto; --com-ia lê as observações com o Haiku
python gerar_relatorio.py                # docs/relatorio-terca.md e .html
```
Além dos testes: guia colada com data invertida, vírgula e observação de protocolo verbal pelo site público; cópia exata da G-0059 digitada como guia nova (tem de dar NÃO ENVIAR); reinício do serviço com o histórico preservado; MCP chamado por HTTPS de fora do servidor.

### Quanto tempo levou

Ver `docs/DIARIO.md`. [Leticia: preencher as suas horas de leitura, decisão e revisão.]

### Perguntas feitas à banca

`docs/PERGUNTAS.md`: validade máxima (sem data de concessão), data de referência da conferência (lançamento), e "confere o que a guia declara".

## Rodar localmente

```bash
python -m venv .venv && .venv/Scripts/activate      # Windows; no Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                  # opcional: ANTHROPIC_API_KEY= para ligar a IA
streamlit run app/app.py
```
Sem chave, o site roda com a IA desligada: observações vão para leitura humana.

## Publicar na VPS

`deploy/instalar.sh` (usuário próprio, venv, testes, dois serviços systemd: site na porta 8502 e MCP na 8503, ambos só locais), `deploy/Caddyfile.bloco` (HTTPS automático e as duas rotas). A chave fica em `/etc/vitalis/env`, `root:vitalis 640`.

## Estrutura

```
normalizador.py       formato: datas BR, vírgula, campos vazios, chave de duplicata
observacao.py         IA (Haiku) → sinais; cache; falha → "não lida"
motor.py              as regras; OK / CORRIGIR / NÃO ENVIAR
servico.py            fonte única: consultar_regra + verificar_guia
verificar_lote.py     lote das 80 + resumo
gerar_relatorio.py    relatório semanal (md + html)
app/app.py            site (Streamlit)  ·  app/armazenamento.py  histórico (SQLite)
mcp_server/server.py  MCP (stdio + HTTP)
.claude/skills/conferir-guia/SKILL.md   Skill
.mcp.json             registro do MCP para o Claude Code
prompts/observacao.md prompt de extração da IA
tests/                78 testes + gabarito independente
dados/                guias.csv, regras_convenio.json, dicionario.html (fictícios, da banca)
deploy/               systemd + Caddy + instalar.sh
docs/                 DIARIO.md, PERGUNTAS.md, relatorio-terca.md
```
