# Diário de horas e decisões

| Data | Bloco | O que foi feito | Horas |
|---|---|---|---|
| 20/09/2026 | Núcleo v1 | normalizador, motor binário, batch, relatório, app Streamlit, SQLite (construído com IA, revisado) | ~2,5 h de agente |
| 20/09/2026 | Avaliação | plano v1 (FastAPI/Supabase/Vercel) vs Maya (Streamlit) vs avaliador independente; decisão: VPS + Streamlit + 3 estados + IA no link | ~1,5 h |
| 20/09/2026 | Bloco A | motor com 3 estados, prazo até a data da conferência, duplicata 1x, sinais da IA; observacao.py (Haiku, cache, queda segura); servico.py (fonte única); gabarito independente; 61 testes | ~2 h de agente |

Horas DELA (leitura, decisões, revisão do gabarito): preencher.

## Decisões minhas (para o README)
1. Três estados nomeados pela ação da clínica: OK / CORRIGIR / NÃO ENVIAR. "Recusar" seria prever o convênio sem fonte.
2. A IA só marca caixinhas; a regra decide. Sem IA, a guia vai para leitura humana. Nunca aprova sozinha.
3. Prazo de envio contado do atendimento até a data da conferência (o JSON diz "para a guia chegar ao convênio"). A fórmula anterior (lançamento − atendimento) nunca disparava.
4. Duplicata: a cópia não vai e a original ganha alerta; o valor conta uma vez por par.
5. Gabarito das 80 escrito por implementação independente e revisado à mão, ao lado do teste de regressão.
6. Hospedar no meu servidor em vez de plano grátis que dorme e apaga o histórico.

## O que ficou de fora
- Regra "validade máxima da autorização" (30/45/60 dias): o CSV não tem a data de emissão. Perguntado à Expert.
- Integração com a API do sistema de gestão: não existe nesta prova; o MCP é a porta onde ela encaixaria.
- Feriados no cálculo de dias úteis da autorização verbal.
| 20/09/2026 | Bloco B | app com 3 estados + urgentes + guia nova (formulário/texto/CSV) checando duplicata no lote e no histórico; armazenamento com decisão completa; deploy na VPS (user vitalis, venv, systemd, Caddy, chave em /etc/vitalis/env); persistência provada após restart | ~1,5 h de agente |
| 21/09/2026 | Ajuste | 3 esclarecimentos da Expert aplicados: validade máxima fora (documentado); conferência do lote na data de lançamento de cada guia (prazo de envio recalculado, 0 urgentes no lote); sem inferência entre guias. Gabarito regenerado, 63 testes | ~40 min de agente |
| 21/09/2026 | UX | painel redesenhado: filtros laterais (busca guia/paciente, decisão, unidade, convênio, profissional, procedimento, tipo, prazo), cartões, box "Prazo de envio vence em 7 dias", detalhe da guia, página "Regras dos convênios"; ação explícita por tipo de NÃO ENVIAR | ~1 h de agente |
| 21/09/2026 | UX 2 | Lista de correções por unidade (Fazer / Por quê, filtro dias para enviar); Relatório semanal com filtro por semana de lançamento e subtítulo limpo; painel sem box de prazo, box "O que a conferência encontrou" explicando que não vem da planilha; escape de R$ no Streamlit | ~50 min de agente |
| 21/09/2026 | UX 3 | Relatório com "Decisões desta semana", termos (Recuperável se corrigir / Faturar particular), glossário e ⓘ nos cartões; IA na barra lateral com contagem; Lista de correções com filtro por tipo e botão "Ver na lista de correções" em cada ação do relatório (navegação por estado) | ~45 min de agente |
| 21/09/2026 | Bloco C | MCP (SDK mcp 2.x) com 3 tools, stdio + HTTP publicado em /mcp na VPS (serviço próprio + rota no Caddy), 7 testes de ponta a ponta; Skill conferir-guia; .mcp.json; README "Como fiz"; prompts/construcao.md; roteiro do vídeo e respostas dos 8 campos em docs/ENTREGA.md; revisão independente do código em andamento | ~1,5 h de agente |
| 21/09/2026 | Revisão | revisor independente: contas do lote batem ao centavo (0 divergências em 80 com reimplementação própria); 20 achados corrigidos: último dia do prazo vale (< 0), sinal "código errado" não esconde cobertura, procedimento vazio/fora da tabela vira CORRIGIR, desempate de ids sem número, duplicata só com carteirinha+data, parser preserva ";", aliases ambíguos removidos, guardas de tipo, "até None", trivial sem pontuação, relatório (plural, numeração, "em" data), 80 hardcoded, slider zerado no atalho, filtro por lista. 78 testes | ~1 h de agente |
| 22/09/2026 | UX 4 | página "MCP" humana (o que é, 3 ferramentas com entrada/saída real, bloco "copie e envie para a sua IA", comando de 1 linha do Claude Code por HTTP, configs) e página "Documentos" com download da Skill, README, relatório, regras, prompt, .mcp.json; todas as 7 páginas renderizadas sem exceção via AppTest | ~45 min de agente |
| 22/09/2026 | UX 5 | página MCP refeita no estilo Zernio: botões "Abrir no Claude / ChatGPT / Perplexity" (mensagem pré-preenchida), "Instalar no Cursor / VS Code" (deep link), "copiar e colar", uma linha do Claude Code, exemplo de guia colada com a resposta, 3 ferramentas em cartões, detalhes em blocos recolhidos; AppTest: 0 exceções, 5 botões | ~40 min de agente |
| 22/09/2026 | Fechamento | Documentos só para a clínica; página MCP com passo a passo de uso no dia a dia; Skill, README e MCP neutros de fornecedor; repositório público criado; Leticia testou Skill + MCP no Claude e no ChatGPT: funcionou. Ferramenta FECHADA. | ~1 h de agente |
