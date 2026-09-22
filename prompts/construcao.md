# Prompts usados na construção

A prova pede os prompts no repositório. Aqui estão os que moldaram o projeto, em ordem.
O prompt de produção (o único que roda em runtime) é `prompts/observacao.md`.

## 1. Plano de ação (20/09/2026)
> "Preciso que crie um plano de ação para executarmos tudo o que estão solicitando neste link. Me entregue em uma URL explicando tudo o que vamos fazer, passo a passo de maneira técnica de um lado e do outro lado explicando de maneira simples cada etapa, cada ferramenta, cada sistema, cada linguagem de programação."

Resultado: plano v1 (FastAPI + Supabase + Vercel), depois descartado.

## 2. Avaliação externa da arquitetura (20/09)
> "Seja MUITO criterioso quanto essas alegações [Streamlit + Hugging Face vs Vercel + Supabase] pois eu quero, nessa entrevista, ser coerente e entregar realmente o que vai ser melhor, não apenas em estrutura, mas também em custo. Chame [um avaliador] para uma dupla avaliação externa para chegarmos na MELHOR solução. E não na mais fácil OU na mais difícil."

Brief entregue ao avaliador independente: comparar duas propostas, rodar os testes, julgar cada alegação, recomendar UMA arquitetura com custo em R$/mês, risco de o link cair no dia da entrevista e o que uma consultora não-dev consegue explicar em 2 minutos. Resultado: núcleo Python + Streamlit no meu servidor, três estados, IA dentro do link, prazo até a data da conferência.

## 3. Motor com três emendas (20/09, Bloco A)
> "Motor com 3 estados OK / CORRIGIR / NÃO ENVIAR; prazo de envio medido do atendimento até a data da conferência; duplicata contada 1 vez por par; a IA só marca caixinhas (sinais) e o motor decide; falha da IA vira 'não lida'; gabarito das 80 guias gerado por implementação que NÃO importa o motor."

## 4. Camada de IA (20/09)
> "observacao.py com claude-haiku-4-5, temperatura 0, JSON com chaves fixas, cache por hash do texto, timeout curto; sem chave ou erro devolve nao_lida=True; testes com dublê nos 5 casos reais."

## 5. Esclarecimentos do Asafe (Expert Integrado) aplicados (21/09)
> "1. Validade da autorização: o CSV só tem a data final. 2. Simula a conferência na data de lançamento; o prazo de envio conta da data do atendimento. 3. As 80 guias são o recorte de agosto. Confere o que a guia declara."

Resultado: `data_ref` por guia = data de lançamento; validade máxima fora; sem inferência entre guias.

## 6. UX (21/09, quatro rodadas, pedidos meus)
> "Não gostei do nome 'O que morre essa semana'. Urgente significa o quê? Por que existe 'Não enviar'? Melhorias nos filtros: unidade, convênio, profissional... A UX e UI precisa ser um ponto a ser olhado."

> "Se tiver um 'corrigida no sistema' a ferramenta deveria puxar essa correção pela API. Não faz sentido. O que dá para fazer é ter um guia DO QUE deve ser alterado nas guias que precisam de correção, em um lugar de fácil acesso."

> "'Relatório de terça' muda para 'Relatório semanal'. Deve ser possível filtrar as semanas. O dono precisa bater o olho em números e ter decisões mais na mão."

> "As informações em 'Top 3 ações da semana' precisam poder ser filtradas em 'Lista de correções'."

## 7. MCP e Skill (21/09, Bloco C)
> "MCP com consultar_regra, verificar_guia e resumo_lote, expondo as funções de servico.py sem lógica própria, em dois transportes: stdio para instalar e HTTP publicado na VPS. Skill para a recepcionista colar a guia como escreveu e receber selo, por quê e o que fazer."
