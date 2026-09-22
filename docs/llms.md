# Vitalis · Conferência de guias de convênio — guia completo para assistentes de IA (llms.md)

> Este arquivo é para ser lido por um modelo de linguagem. Ele descreve tudo que um assistente
> precisa para usar o MCP da Clínica Vitalis e conferir guias de convênio antes do envio.
> Dados fictícios fornecidos por uma prova técnica; nenhum paciente ou convênio é real.

## O que é

A Clínica Vitalis (fisioterapia e ortopedia, 3 unidades: Centro, Norte, Sul) lança cerca de 900 guias de
convênio por mês. Sem conferência, o erro só aparece quando o convênio glosa, 60 dias depois. Este serviço
confere cada guia antes do envio e devolve uma decisão auditável, em português de recepção:

- **OK**: pode ir ao convênio.
- **CORRIGIR**: falta algo que a recepção resolve no sistema de gestão antes do envio (CID, número da
  autorização, autorização vencida a renovar, sessão acima do limite, código de procedimento errado).
- **NÃO ENVIAR**: o convênio não cobre o procedimento (faturar como particular), o paciente pediu particular,
  ou a guia é cópia de outra já lançada (descartar).

Quem decide é um motor de regras determinístico (`motor.py`). A IA só lê o texto livre que a recepcionista
escreveu na guia e o transforma em sinais; nunca aprova sozinha. O assistente que usa o MCP também não decide:
ele chama a ferramenta e transmite a resposta.

## Endereço do MCP

- URL: `https://vitalis.geaia.com/mcp`
- Transporte: streamable HTTP (JSON-RPC 2.0, respostas em JSON). Sem autenticação.
- Também disponível por stdio a partir do repositório: `python mcp_server/server.py`.
- Claude Code: `claude mcp add --transport http vitalis-guias https://vitalis.geaia.com/mcp`
- Claude Desktop (`claude_desktop_config.json`): `{"mcpServers": {"vitalis-guias": {"url": "https://vitalis.geaia.com/mcp"}}}`

## Ferramentas

### consultar_regra(convenio: string, procedimento_codigo?: string) → objeto
O que um convênio exige e cobre. Convênios conhecidos: `Vitalcard`, `Saúde Interior`, `Plano Bem`
(comparação sem diferença de maiúsculas).
Resposta com `ok: true`: `convenio`, `campos_obrigatorios` (lista), `validade_maxima_autorizacao_dias`
(informativo; não verificável, o CSV não tem data de concessão), `limite_sessoes_por_autorizacao`,
`prazo_envio_dias` (dias contados do atendimento para a guia chegar ao convênio), `procedimentos_cobertos`
(lista de códigos), `observacao` (regra em texto do convênio), `versao_regras`. Com `procedimento_codigo`:
`procedimento.{codigo, descricao, valor_referencia, na_tabela, coberto}`.
Resposta com `ok: false`: `erro` e `convenios_conhecidos`.

### verificar_guia(guia: objeto) → objeto
Confere uma guia como a recepção lançou. Campos do objeto `guia` (todos strings; qualquer um pode faltar):
`id_guia`, `unidade`, `data_atendimento`, `paciente`, `convenio`, `carteirinha`, `cid`,
`procedimento_codigo`, `procedimento_descricao`, `numero_autorizacao`, `autorizacao_validade`,
`autorizacao_sessoes_limite`, `sessao_numero_na_autorizacao`, `profissional`, `profissional_registro`,
`valor`, `observacao_recepcao`, `data_lancamento`.
Aceita datas `dd/mm/aaaa` ou `aaaa-mm-dd`, valor com vírgula (`62,00`), espaços sobrando. Nunca dá erro:
dado ilegível vira CORRIGIR "dado inválido". A data de referência da conferência é `data_lancamento`;
sem ela, hoje. Se já existir no lote uma guia com a mesma carteirinha, autorização, data e procedimento,
esta é tratada como cópia (NÃO ENVIAR).
Resposta: `ok: true`, `decisao` (`OK` | `CORRIGIR` | `NÃO ENVIAR`), `motivos` (lista de frases),
`correcoes` (lista, o que fazer), `alertas` (avisos que não reprovam: urgência de prazo, divergência de
limite ou valor, guia remarcada), `tipos` (categorias), `valor`, `valor_em_risco` (quando CORRIGIR),
`valor_reclassificar` (quando NÃO ENVIAR; cópia vale 0), `urgente` (≤ 7 dias para o prazo de envio),
`dias_para_prazo`, `normalizacoes` (formatos corrigidos), `sinais` (o que a IA leu na observação, ou null),
`data_referencia`, `versao_regras`.

### resumo_lote() → objeto
`ok: true` e `resumo` com os números do lote de agosto (80 guias): `total_conferidas`, `ok`, `corrigir`,
`nao_enviar`, `valor_ok_total`, `valor_em_risco_total`, `valor_reclassificar_total`, `urgentes` (lista),
`problemas_por_tipo` (mapa tipo → quantidade), `por_unidade`, `por_convenio`, `com_ia`.

## Regras dos convênios (versão agosto/2026)

| Convênio | Campos obrigatórios | Limite de sessões por autorização | Prazo de envio | Cobre | Observação |
|---|---|---|---|---|---|
| Vitalcard | número e validade da autorização, registro do profissional, carteirinha, CID | 10 | 30 dias | 50000470, 50000560, 50000012, 20103301 | reavaliação médica a cada 10 sessões; nova autorização a cada reavaliação |
| Saúde Interior | número e validade da autorização, registro do profissional, carteirinha | 20 | 45 dias | 50000470, 50000012, 20103301, 40201015 | aceita autorização verbal com protocolo por até 5 dias úteis, desde que o número seja lançado antes do envio |
| Plano Bem | número e validade da autorização, registro do profissional, carteirinha, CID | 12 | 30 dias | 50000470, 50000560, 50000012 | não cobre consulta médica; consulta é faturada como particular |

Procedimentos: 50000470 sessão de fisioterapia musculoesquelética (R$ 62), 50000560 sessão de fisioterapia
neurofuncional (R$ 70), 50000012 reavaliação fisioterapêutica (R$ 55), 20103301 consulta ortopédica (R$ 90),
40201015 infiltração articular (R$ 140).

## Como o motor decide (para explicar a resposta)

1. Campo obrigatório do convênio vazio → CORRIGIR. Exceção: Saúde Interior sem número mas com protocolo
   verbal na observação → CORRIGIR "lançar o número até <5 dias úteis do atendimento>".
2. Validade da autorização anterior à data do atendimento → CORRIGIR "autorização vencida". Se a observação
   diz que há autorização nova com validade que cobre a data → CORRIGIR "lançar o número da autorização nova".
3. Sessão (posição declarada na guia) acima do limite do convênio → CORRIGIR. O limite vem da regra do
   convênio, não do que a guia digitou; divergência vira alerta.
4. Código do procedimento vazio → CORRIGIR; fora da tabela → CORRIGIR (erro de digitação); na tabela mas não
   coberto pelo convênio → NÃO ENVIAR (faturar particular). Observação "procedimento realizado foi outro" →
   CORRIGIR "lançar o código certo".
5. Paciente pediu particular (observação) → NÃO ENVIAR.
6. Prazo de envio: `prazo_envio_dias − (data da conferência − data do atendimento)`. Negativo → CORRIGIR
   "prazo de envio perdido"; 0 a 7 → alerta URGENTE.
7. Guia igual a outra já lançada (carteirinha + autorização + data + procedimento) → a nova é NÃO ENVIAR
   "cópia"; a original recebe aviso. O valor conta uma vez.
8. Prioridade: NÃO ENVIAR > CORRIGIR > OK. Todos os motivos são listados.
9. Sem IA, observação fora da rotina → CORRIGIR "requer leitura humana". Com IA, a observação vira sinais
   (`autorizacao_nova`, `validade_nova`, `protocolo_verbal`, `faturar_particular`, `codigo_errado`,
   `procedimento_real`, `remarcada_de`, `irrelevante`); falha da IA → CORRIGIR "observação não lida".

## Como responder ao usuário (formato recomendado)

```
🟠 CORRIGIR · G-NOVA-0002 · Saúde Interior · R$ 62,00
Por quê: autorização verbal (protocolo 990421) sem número lançado; o Saúde Interior aceita verbal por 5 dias úteis (até 04/09).
Fazer: lançar o número definitivo da autorização no sistema até 04/09.
```
Uma linha por motivo em "Por quê", copiada de `motivos`; "Fazer" copiado de `correcoes`. Nunca dizer
"pode enviar" para CORRIGIR ou NÃO ENVIAR. Se a resposta tiver `ok: false`, dizer o erro e pedir o dado.

## Exemplo de chamada crua (JSON-RPC)

```
POST https://vitalis.geaia.com/mcp
Content-Type: application/json
Accept: application/json, text/event-stream

{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"verificar_guia","arguments":{"guia":{
 "convenio":"Plano Bem","carteirinha":"626441373","cid":"M51.1","procedimento_codigo":"20103301",
 "numero_autorizacao":"AUT320436","autorizacao_validade":"23/08/2026","sessao_numero_na_autorizacao":"1",
 "profissional_registro":"CRM-SP 112390","valor":"90,00","data_atendimento":"06/08/2026"}}}}
```
Resposta: `result.content[0].text` é um JSON com `decisao: "NÃO ENVIAR"`, motivo "procedimento 20103301 não é
coberto pelo Plano Bem", correção "não enviar ao convênio: faturar como particular".

## Onde está o código

Repositório público com o site (Streamlit), o MCP (`mcp_server/server.py`), a Skill
(`.claude/skills/conferir-guia/SKILL.md`), o motor de regras, os testes e o README "Como fiz".
Site: https://vitalis.geaia.com · MCP: https://vitalis.geaia.com/mcp
