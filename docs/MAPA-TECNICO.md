# MAPA TÉCNICO PARA DEFESA · Prova 2 Expert Integrado (Clínica Vitalis)

Para: Leticia · Uso: estudar antes da entrevista e defender cada decisão sozinha.
Como usar: leia peça por peça. Cada uma tem 4 blocos (o que é, como foi feita, onde roda,
por que assim) e fecha com UMA frase de defesa pronta para falar em voz alta.

Legenda de status:
- **[CONSTRUÍDO]** = já existe e roda (F1: núcleo, testes, batch, relatório).
- **[PLANEJADO]** = desenhado e decidido, será construído (F2: MCP e Skill · F3: app e repo).

---

## A FRASE-MÃE (se decorar uma coisa só, é esta)

"Regra objetiva é código com teste. IA só entra onde tem linguagem humana, e mesmo aí
ela não aprova nada sozinha: no máximo explica e recomenda. Quem aprova exceção é gente."

Tudo abaixo é desdobramento disso.

---

## ONDE CADA COISA RODA (desfazendo o mito do servidor)

Pergunta que você fez: "isso roda no servidor da Maya?". Resposta: **não**. O servidor da
EAIA foi só a bancada onde o time montou e testou, como a oficina onde o carro foi
construído. O que é ENTREGUE e ACESSADO na prova não depende dele em nada:

| Peça | Onde roda de verdade | Quem aciona |
|---|---|---|
| Código-fonte | Servidores do GitHub (repo público) | Qualquer um que abrir o link |
| Ferramenta interativa | Servidores do Streamlit Community Cloud | Avaliador abre a URL |
| Batch das 80 guias + testes | Na máquina de quem clonar o repo (Python puro) | `python3 verificar_lote.py` |
| MCP server | Na máquina do avaliador, dentro do Claude dele | Claude chama as tools |
| Skill | Na conta Claude de quem instalar | Operadora cola a guia |
| IA (leitura de texto livre) | O próprio Claude que hospeda a Skill | Nenhuma API key minha |

Teste mental que você pode falar na entrevista: "se o meu computador e qualquer servidor
meu sumirem amanhã, a prova continua 100% no ar e 100% instalável. O projeto vive no repo
público e em serviços grátis que fazem deploy direto dele."

---

## AS 10 PEÇAS

### 1. Linguagem: Python 3, só biblioteca padrão **[CONSTRUÍDO]**

**O que é.** Todo o núcleo usa apenas o que já vem instalado com o Python: `csv`, `json`,
`datetime`, `unittest`. Zero `pip install` para rodar a conferência.

**Como foi feito.** Três módulos pequenos e legíveis: `normalizador.py` (arruma formato),
`motor.py` (aplica regra), `verificar_lote.py` (roda o lote). Mais `test_verificador.py`
(testes) e `gerar_relatorio.py` (relatório). Funções puras: entra dado, sai decisão.

**Onde roda.** Qualquer máquina com Python 3. O avaliador clona e roda com um comando.

**Por quê (trade-off).** Zero dependência = nada quebra por versão de biblioteca, instala
em qualquer lugar, e cada linha é explicável. Node/JS não ganharia nada aqui: o problema é
comparar datas, números e listas. Framework seria peça a mais para defender sem retorno.

**Defesa:** "Escolhi Python puro porque conferir guia é comparar data, número e lista.
Para isso não preciso de framework, e assim eu explico o código linha a linha."

### 2. Normalizador (camada 1) **[CONSTRUÍDO]**

**O que é.** A primeira peneira: pega a guia do jeito que a recepção digitou e arruma SÓ o
formato, sem decidir nada. Data brasileira 26/08/2026 vira 2026-08-26; valor "62,00" vira
número 62.0; espaço sobrando sai; e ele monta a chave de duplicata (carteirinha +
autorização + data + procedimento) que a camada 2 usa.

**Como foi feito.** `normalizador.py`, uma função pequena por tipo de campo. Regra de ouro
do arquivo: NUNCA levanta exceção. Dado ilegível (data impossível, valor sem número) entra
numa lista `_erros` e a guia segue adiante para virar PENDENTE com motivo claro, em vez de
derrubar o sistema. No lote real, 3 guias vieram com formato fora do padrão e foram
corrigidas automaticamente sem virar pendência.

**Onde roda.** Dentro de todos os consumidores (batch, MCP, Skill, app). É sempre o
primeiro passo do pipeline.

**Por quê (trade-off).** Separar FORMATO de REGRA. A causa raiz do caso Vitalis é erro de
digitação da recepção; se eu conferir regra em cima de dado torto, gero veredito errado.
E "erro tratado, nunca quebra" é critério explícito da prova.

**Defesa:** "Sujeira de digitação não pode virar veredito errado nem derrubar o sistema.
O normalizador arruma o formato e, quando o dado é ilegível, marca a guia como pendente
com o motivo, em vez de quebrar."

### 3. Motor de regras determinístico (camada 2) **[CONSTRUÍDO]**

**O que é.** O coração. Recebe a guia limpa + o arquivo `regras_convenio.json` e devolve:
OK ou PENDENTE, com TODOS os motivos (não só o primeiro), a correção sugerida de cada um
e o valor em risco. São 8 checagens: dado inválido, convênio desconhecido, campos
obrigatórios POR convênio, autorização vencida, sessão acima do limite, procedimento não
coberto, prazo de envio, duplicata. Observação de texto livre ele não interpreta: marca
"requer leitura" (isso é trabalho da IA, na Skill).

**Como foi feito.** `motor.py`, uma função pura `verificar(guia, regras) -> Decisao`. Não
lê disco, não acessa rede, não usa IA. As regras moram no JSON, nunca no código: convênio
novo entra como um bloco novo no JSON, zero linha de código. Duas decisões minhas dentro
dele: (a) a fonte de verdade do limite de sessões é o JSON do convênio, não o que a
recepção digitou na guia (divergência vira alerta próprio); (b) duplicata nunca some em
silêncio: vira PENDENTE apontando o par.

**Onde roda.** Em todo consumidor. Uma lógica, quatro portas: batch, MCP, Skill, app.

**Por quê (trade-off).** Data vencida é data vencida: comparação em código, com teste, é
auditável, grátis de rodar e sempre dá a mesma resposta. Num prompt de IA seria caro,
lento e improvável: eu não conseguiria PROVAR o veredito. E engine de regras de mercado
seria bazuca para matar formiga, impossível de explicar por dentro.

**Defesa:** "Regra de convênio é código com teste, não prompt. E o motor devolve todos os
motivos de uma vez, com a correção do lado, porque o objetivo da clínica é a recepção
corrigir ANTES do envio, não descobrir um erro por vez depois da glosa."

### 4. Testes (32 passando) **[CONSTRUÍDO]**

**O que é.** 32 testes automáticos. Cada tipo de erro real das 80 guias virou um caso de
teste com resposta esperada: guia com autorização vencida TEM que sair pendente com esse
motivo; guia limpa TEM que sair OK.

**Como foi feito.** `test_verificador.py` com `unittest` (também da biblioteca padrão).
Usa as próprias guias-problema do caso como gabarito. Roda com `python3 -m unittest`.

**Onde roda.** Na máquina de quem clonar o repo. Os testes vão públicos junto com o código.

**Por quê (trade-off).** É a resposta à pergunta "como você sabe que está certo?". E é
proteção de futuro: se uma mudança em regra quebrar outra sem querer, um teste acusa antes
do convênio acusar.

**Defesa:** "Como sei que está certo? 32 testes automáticos que usam as próprias guias
problemáticas como gabarito. Qualquer mudança que quebre uma regra derruba um teste na
hora, antes de chegar no convênio."

### 5. Batch + relatório de terça **[CONSTRUÍDO]**

**O que é.** `verificar_lote.py` passa as 80 guias pelo núcleo e grava `resultados.csv` e
`resultados.json` (cada guia com veredito, motivos, correção). `gerar_relatorio.py` monta
o relatório de terça do Dr. Renato em uma página: 80 conferidas, 43 OK, 37 pendentes,
R$ 2.762,00 em risco, quebra por tipo, por unidade e por convênio, e top 3 ações da semana.

**Como foi feito.** Leitura do CSV, índice de duplicatas pela chave do normalizador, e um
detalhe importante: a data de referência do lote é PARÂMETRO explícito e documentado
(`--data-ref 2026-09-01`). Decisão minha, para o resultado ser reprodutível: o avaliador
roda o mesmo comando e chega nos MESMOS números. Em produção seria a data do dia.

**Onde roda.** Linha de comando, qualquer máquina, sem internet.

**Por quê (trade-off).** O relatório é o entregável de NEGÓCIO: linguagem de dono de
clínica, número antes de adjetivo, e cada pendência já com o que fazer. Ele sai do mesmo
motor que confere guia a guia, então relatório e veredito nunca divergem.

**Defesa:** "R$ 2.762 em risco não é estimativa: é a soma do valor das 37 guias pendentes,
calculada pelo mesmo motor que confere cada guia. Qualquer pessoa reproduz o número
rodando um comando com a data de referência documentada."

### 6. MCP server (3 tools) **[PLANEJADO · F2]**

**O que é.** MCP (Model Context Protocol) é o padrão aberto do mercado para dar
ferramentas a um assistente de IA: o Claude passa a poder CHAMAR funções minhas em vez de
chutar respostas. Meu servidor MCP expõe o verificador como 3 tools:
1. `consultar_regra(convenio, procedimento)`: devolve campos obrigatórios, cobertura,
   validade, limite de sessões, prazo de envio e observações (a exceção da autorização
   verbal do Saúde Interior sai daqui).
2. `verificar_guia(campos)`: devolve `{decisao, motivos, correcoes, valor_em_risco}`.
   Input com problema (campo faltando, data inválida, convênio desconhecido) responde
   estruturado, nunca erro cru de programa.
3. `resumo_lote()`: os números do relatório de terça, a partir do `resultados.json`.
A prova pede no mínimo 2; entrego 3.

**Como foi feito (será).** SDK oficial `mcp` da Anthropic (FastMCP), em Python. É a ÚNICA
dependência instalável do projeto inteiro. Transporte stdio: o Claude inicia o meu script
como processo local e conversa com ele por entrada e saída de texto. Sem porta de rede,
sem servidor exposto, sem chave.

**Onde roda.** Na máquina do avaliador, dentro do Claude dele. Instalação = um bloco de
configuração no `claude_desktop_config.json` (ou `.mcp.json`) apontando para o script; o
README traz o bloco pronto para copiar. Antes de entregar, a instalação é testada num
ambiente limpo seguindo SÓ o README.

**Por quê (trade-off).** stdio é a forma mais simples e mais segura de MCP: roda local,
nada para pagar, nada para vazar. E a tool não "decide com IA": ela chama o MESMO motor
determinístico. O MCP é uma porta, não um cérebro novo.

**Defesa:** "O MCP é uma porta padronizada para o mesmo motor: o Claude pergunta, o meu
código responde. Roda na máquina de quem instala, por stdio, sem servidor exposto e sem
nenhuma chave."

### 7. Skill do Claude (`verificar-guia`) **[PLANEJADO · F2]**

**O que é.** Skill é um pacote de instruções (um arquivo `SKILL.md` com o passo a passo)
que ensina o Claude a executar um fluxo do meu jeito. A skill `verificar-guia`: a
operadora COLA a guia do jeito que a recepção escreveu, o Claude estrutura os campos,
chama a tool `verificar_guia` do MCP e devolve OK ou pendente + motivo + correção. É AQUI,
e só aqui, que a IA lê o texto livre da observação da recepção ("trouxe autorização nova",
"autorizado por telefone, protocolo 771203"). E mesmo aqui vale a trava: a IA nunca
transforma pendente em OK; ela explica a exceção, cita a regra e recomenda o passo.

**Como foi feito (será).** Pasta da skill dentro do repo; instala copiando para a pasta de
skills do Claude. O README documenta os 2 comandos.

**Onde roda.** No Claude da conta de quem instalar: na minha, para demonstrar; na do
avaliador, para ele testar com guia nova.

**Por quê (trade-off).** É exigência literal da prova. E resolve o "onde entra IA" com
custo zero e sem chave: a IA da solução É o Claude que hospeda a skill. Não existe chamada
de API no meu código, logo não existe segredo para guardar. Se a IA estiver indisponível,
a guia fica pendente como "requer revisão humana": o sistema degrada com segurança, nunca
aprova às cegas.

**Defesa:** "A IA entra exatamente onde tem linguagem humana: a observação da recepção.
E mesmo aí ela não aprova; ela explica e recomenda. Quem aprova exceção é gente. Se a IA
cair, a guia fica pendente para revisão humana; o sistema nunca aprova às cegas."

### 8. Ferramenta interativa na web **[PLANEJADO · F3 · sua decisão de 20/09: opção B]**

**O que é.** A URL pública que o avaliador abre no navegador: vê as 80 guias com veredito
e filtros, e tem um formulário para colar uma guia NOVA e receber a decisão na hora. É a
prova viva de que a solução aguenta guia que nunca viu.

**Como foi feito (será).** App em Streamlit: biblioteca Python que transforma um script
em página web com formulário, sem eu escrever HTML ou JavaScript. O app IMPORTA o mesmo
`motor.py` e `normalizador.py` do repo. Nenhuma regra é reescrita: uma lógica só, e a
quarta porta do mesmo motor.

**Onde roda.** Streamlit Community Cloud, o serviço grátis da própria Streamlit: eu
conecto o repo público do GitHub, ele faz o deploy sozinho a cada push e me dá uma URL
https. Sem cartão de crédito, sem chave, sem servidor meu. Limitação honesta para dizer se
perguntarem: app grátis hiberna sem uso e leva alguns segundos para acordar na primeira
visita; para uma prova isso é aceitável, e eu acordo o app antes da entrevista.
Alternativa equivalente se precisar: Hugging Face Spaces.

**Por quê (trade-off).** Junta as três restrições de uma vez: interativa (minha decisão),
grátis e sem segredo (deploy direto de repo público), e em Python (reusa o motor sem
traduzir nada). A alternativa de traduzir o motor para JavaScript e servir estático
criaria DUAS implementações da mesma regra para manter iguais: risco de divergência que
não aceito num verificador.

**Defesa:** "O app é uma casca de formulário em cima do mesmo motor que roda o lote e o
MCP. Uma lógica, quatro portas. O Streamlit Community Cloud publica direto do repo
público, de graça, sem cartão e sem nenhuma chave."

### 9. Repo público no GitHub (conta dela) **[PLANEJADO · F3]**

**O que é.** Todo o projeto num repositório público na MINHA conta: código, dados da
prova, MCP, Skill, app, README "Como fiz" e o relatório. Nome sugerido:
`vitalis-conferencia-guias`.

**Como foi feito (será).** Repo novo, histórico nasce limpo e datado: nada reaproveitado
de projeto anterior (exigência "nasce para a prova"). O README conta com honestidade que
eu operei minha estrutura de IA para construir (usar IA É o esperado da vaga) e registra
as decisões que são MINHAS: as 6 do projeto, o que ficou de fora e por quê, como testei,
quanto tempo levou.

**Onde roda.** Servidores do GitHub. É também a origem do deploy: o Streamlit Cloud lê
direto dele.

**Por quê (trade-off).** A prova exige repo público. E público aqui é vantagem dupla:
habilita o deploy grátis e funciona como argumento de qualidade: dá para abrir qualquer
arquivo na entrevista e explicar.

**Defesa:** "Está tudo público porque não tem nada a esconder: nenhuma chave, nenhum dado
real de paciente, e cada regra é legível. Poder ser auditado é parte da solução."

### 10. Publicação sem segredo (gitleaks + .gitignore) **[PLANEJADO · F3, política desde o dia 1]**

**O que é.** A garantia de que nenhuma senha, token ou chave entra no repo público.

**Como foi feito.** Em duas camadas:
1. **Por construção:** a arquitetura NÃO TEM segredo. Sem banco (logo sem senha de banco),
   sem chamada de API de IA no código (logo sem API key): a IA é o Claude de quem instala
   a Skill. Não dá para vazar o que não existe.
2. **Por verificação:** `gitleaks`, scanner open source que varre o repositório e o
   histórico procurando padrões de credencial (chaves de API, tokens, senhas), roda antes
   de todo push. E o `.gitignore` bloqueia arquivos locais de entrarem por acidente.

**Por quê (trade-off).** A forma mais segura de não vazar chave é não precisar de chave.
A varredura é o cinto de segurança por cima da decisão de arquitetura, não o plano A.

**Defesa:** "Meu repo não guarda segredo porque a arquitetura não precisa de nenhum: sem
banco e sem API key por construção. E ainda assim um scanner confere tudo antes de cada
publicação. Segurança por construção primeiro, verificação depois."

---

## POR QUE NÃO VERCEL E SUPABASE (sua pergunta, resposta honesta)

Primeiro: sua intuição está certa NO GERAL. Serviço gerenciado (Vercel, Supabase) costuma
ser mais robusto que servidor cru que alguém administra na mão: eles cuidam de segurança,
escala e atualização. Se a escolha fosse "Vercel vs meu servidor caseiro", Vercel ganharia.
Mas aqui a comparação é outra: "serviço gerenciado A vs serviço gerenciado B vs nenhuma
peça". E neste projeto:

**Vercel: questão de encaixe, não de segurança.** A Vercel é excelente, e o ponto forte
dela é aplicação JavaScript (Next.js e parecidos). Python roda lá, mas como função
serverless, um modelo que não é o formato do nosso app interativo. Para usar Vercel bem eu
teria dois caminhos ruins: traduzir o motor para JavaScript (duas implementações da mesma
regra para manter sincronizadas, risco real de divergência num verificador) ou forçar
Python num modelo que não é o forte da plataforma. O Streamlit Community Cloud faz para
app Python exatamente o que a Vercel faz para app Next.js: deploy direto do repo, grátis,
gerenciado. Escolhi o gerenciado que casa com a minha linguagem.

**Supabase: é banco de dados, e este projeto não pede banco.** Supabase é Postgres
gerenciado com autenticação, ótimo quando há muitos usuários gravando dados ao mesmo
tempo. Aqui o dado é um CSV de 80 guias (900/mês na operação real): cabe em arquivo, lido
em milissegundos. Adicionar Supabase traria duas coisas que eu não quero: uma peça a mais
para eu defender sem ganho de capacidade, e uma connection string (uma senha de banco) que
eu teria que guardar em algum lugar, indo direto contra a restrição "repo público sem
segredo". Neste caso específico, o mais simples é literalmente o mais seguro.

**Frase pronta se perguntarem:** "Serviço gerenciado ganha quando substitui trabalho que
eu teria. Aqui ele adicionaria trabalho e uma chave para proteger. Como o dado é pequeno e
a lógica é local, sem banco significa sem segredo, e isso é mais seguro e mais explicável
num repo público."

E fica registrado: se você preferir a pilha Vercel + Supabase e se sentir mais forte
defendendo ela, a decisão é sua: a arquitetura do motor não muda, só a casca e o custo de
explicação. Este mapa recomenda a opção com menos peças porque cada peça a mais é uma
pergunta a mais na entrevista.

---

## COLA DE NÚMEROS (para ter na ponta da língua)

- **80** guias conferidas · **43** OK · **37** pendentes · **R$ 2.762,00** em risco
- Pendências por tipo: **13** autorização vencida · **8** campo obrigatório faltando ·
  **6** sessão acima do limite · **5** procedimento não coberto · **5** observação requer
  leitura · **4** possível duplicata (2 pares: 0027/0057 e 0059/0076)
- **3** guias com formato torto corrigidas automaticamente pelo normalizador (sem virar pendência)
- **32** testes automáticos, todos passando · **8** checagens no motor · **3** convênios no JSON
- Data de referência do lote: **2026-09-01** (parâmetro documentado, reprodutível)
- Volume real da clínica: **900 guias/mês** (por isso arquivo resolve e banco seria excesso)
- Dependência instalável do projeto inteiro: **1** (o SDK `mcp`, só para a fase do MCP)
- Melhor história para contar: a **G-2608-0041** (Saúde Interior sem número de
  autorização, mas com "autorizado por telefone, protocolo 771203"; a regra do convênio
  aceita verbal com protocolo por 5 dias úteis; o sistema aponta a exceção e cobra o
  lançamento do número antes do envio. Determinístico pegou, IA explicou, humano decide.)

---

## CHECAGEM FINAL DE ESTUDO

Você está pronta quando responder, sem olhar este mapa:
1. Por que a IA não decide o veredito? (peças 3 e 7)
2. Como você sabe que os vereditos estão certos? (peça 4)
3. Onde isso roda e quanto custa? (seção "onde cada coisa roda": repo + host grátis +
   Claude do avaliador; custo zero)
4. Por que não usou banco de dados? (seção Vercel/Supabase: 900 guias/mês, sem banco =
   sem chave = repo público limpo)
5. E se chegar um convênio novo? (bloco novo no `regras_convenio.json`, zero código)
6. E se a guia vier quebrada? (peça 2: normalizador trata, guia vira pendente com motivo,
   sistema nunca quebra)
