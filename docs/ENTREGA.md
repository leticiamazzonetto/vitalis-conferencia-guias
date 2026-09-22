# Entrega da prova: roteiro do vídeo e respostas dos 8 campos

## Roteiro do vídeo (≤ 5 min, uma tomada, sem slide)

| Min | Cena | O que dizer (na sua voz) |
|---|---|---|
| 0:00 | Abrir https://vitalis.geaia.com no Painel | "Na primeira prova eu deixei a glosa para a segunda fase. Esta é a segunda fase. 80 guias de agosto conferidas: 46 podem ir, 26 a recepção corrige e valem R$ 1.760, 8 não vão pelo convênio e valem R$ 612 como particular." |
| 0:40 | Aba "Conferir guia" → "Colar texto" → botão | "A recepcionista cola do jeito que escreveu. Data invertida, vírgula, e um bilhete: 'autorizado por telefone, protocolo 990421'. O formato é arrumado sozinho; a IA lê o bilhete e marca 'protocolo verbal'; a regra do Saúde Interior diz que verbal vale 5 dias úteis. Decisão: corrigir, lançar o número até 04/09." |
| 1:40 | Painel → detalhe da G-2608-0030 | **Decisão técnica.** "A regra diz vencida: validade 17/08, atendimento 21/08. Mas a recepção escreveu 'autorização nova, validade 30/09'. A IA transformou isso em duas caixinhas, e a regra, com as caixinhas marcadas, rebaixou de 'pedir autorização' para 'digitar o número que já está no balcão'. A IA nunca decide. Se ela cair, a guia vai para leitura humana. Nove chamadas para 80 guias, centavos." |
| 2:50 | Lista de correções, filtro por unidade | "Isto é o que a recepção de cada unidade faz hoje no sistema de gestão, guia por guia. A correção é lá; aqui a guia é reconferida e vira OK." |
| 3:20 | Relatório semanal → botão "Ver na lista de correções" | "O dono vê as decisões da semana e cada ação abre a lista já filtrada." |
| 3:50 | Terminal: `python -m unittest discover -s tests` + Claude Code com a Skill | "78 testes, incluindo um gabarito escrito fora do motor. E o MCP: a mesma função do site, exposta para um assistente. A recepcionista cola a guia e recebe o selo." |
| 4:30 | Fechar | "Ficou de fora: a validade máxima da autorização, porque o CSV não tem a data de concessão, confirmado com a banca; e a integração com o sistema de gestão, que é onde o MCP encaixa. Levou X horas." |

Gravar em Loom ou OBS, YouTube não listado. Testar o link em janela anônima.

## Respostas para os 8 campos do formulário

**1.1 Onde a gente acessa a sua solução funcionando com as 80 guias**
https://vitalis.geaia.com

**1.2 Como uma guia nova entra e como a decisão sai**
Entra por três portas: formulário no site, texto colado como a recepção escreve (data dd/mm, vírgula no valor, campos faltando) ou CSV exportado do sistema de gestão. Também entra pelo MCP (`verificar_guia`), que é por onde a API do sistema de gestão encaixaria. A decisão sai na hora: OK, CORRIGIR ou NÃO ENVIAR, com o motivo em português e o que fazer, e fica gravada no histórico. A guia nova é comparada com o lote e com o histórico: se for cópia, não vai.

**1.3 O relatório de terça do Dr. Renato**
Página "Relatório semanal" em https://vitalis.geaia.com (com filtro por semana) e o arquivo `docs/relatorio-terca.md` no repositório. [Colar o conteúdo do .md aqui.]

**2.1 MCP**
`mcp_server/server.py`. Três ferramentas: `consultar_regra(convenio, procedimento_codigo)`, `verificar_guia(guia)` e `resumo_lote()`. Lê `dados/regras_convenio.json` e `dados/guias.csv` direto do disco e chama `servico.py`, a mesma função do site. Instalação local: `pip install -r requirements.txt` e abrir o repositório no Claude Code (o `.mcp.json` registra o servidor) ou `claude mcp add vitalis-guias -- python mcp_server/server.py`. Sem instalar: `https://vitalis.geaia.com/mcp` (HTTP). Teste: `python -m unittest tests.test_mcp`.

**2.2 Skill**
`.claude/skills/conferir-guia/SKILL.md`. A pessoa cola a guia como a recepção escreveu; a Skill monta os campos, chama `verificar_guia` no MCP e responde no formato fixo: selo (OK / CORRIGIR / NÃO ENVIAR), por quê, o que fazer.

**3.1 README "Como fiz"**
https://github.com/leticiamazzonetto/vitalis-conferencia-guias#como-fiz

**3.2 Vídeo**
[link não listado]

**3.3 Repositório público**
https://github.com/leticiamazzonetto/vitalis-conferencia-guias

**3.4 Horas de trabalho e ferramentas**
≈ X h (ver docs/DIARIO.md). Python, Streamlit, SQLite, Claude Haiku 4.5 (API), SDK MCP, unittest, Caddy, systemd, Claude Code.
