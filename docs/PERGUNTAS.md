# Perguntas à Expert sobre os dados (dúvida sobre dados ou regras conta a favor)

## Enviadas 20/09/2026
1. `validade_maxima_autorizacao_dias` (30/45/60) sem data de emissão no CSV: como verificar?
2. Autorização vencida / sessão acima do limite: o convênio recusa de vez, ou aceita se a clínica regularizar antes do envio?

## Resposta da Expert, 21/09/2026 (WhatsApp, "vale pra todo mundo")
1. **Validade da autorização**: o CSV só tem a data final; não existe data de concessão. A verificação possível é validade contra a data do atendimento.
   → Efeito: a regra "validade máxima" fica fora, documentado. `consultar_regra` devolve o campo só como informação.
2. **Data da conferência do lote de agosto = data de lançamento de cada guia** ("a guia acabou de ser lançada e ainda não foi enviada"). O prazo de envio conta da data do atendimento.
   → Efeito: `data_ref` deixou de ser 01/09 fixo; cada guia do lote é conferida na sua `data_lancamento` (0 a 3 dias após o atendimento). Nenhuma guia de agosto fica perto do prazo; o bloco "urgentes" vale para a conferência semanal, com referência no dia. A autorização verbal da G-0041 passa a "lançar o número até 27/08" em vez de "prazo já passou".
3. **As 80 guias são o recorte de agosto, não o histórico completo das autorizações. Confere o que a guia declara.**
   → Efeito: nenhuma inferência entre guias (contagem de sessões, reavaliação a cada 10). A duplicata dentro do próprio recorte continua: duas guias que declaram exatamente os mesmos dados são cobrança repetida.

Pergunta 2 (vencida/acima do limite = corrigir ou recusa) segue sem resposta explícita; mantidas como CORRIGIR.
