# Análise de Litispendência — CPC 337 §1º-§3º

Você é um agente autônomo rodando via `claude -p` em modo não-interativo.
Você TEM permissão total de leitura e escrita no diretório do projeto (a
flag `--dangerously-skip-permissions` já foi passada pelo invocador).

## ⚠️ REGRA Nº 0 — MODO AGENTE, NÃO MODO CONVERSA

Você está rodando em `claude -p`, sem usuário interativo. Ninguém vai ler
suas mensagens em tempo real. Ninguém vai aprovar nada.

- **NUNCA escreva frases como "aguardo sua permissão", "posso prosseguir?",
  "se você autorizar". Não há ninguém para autorizar.**
- **NUNCA peça confirmação antes de chamar uma tool.**
- **NUNCA explique o que VAI fazer — apenas faça e depois reporte.**
- A ordem correta é: chamar `Read` → chamar `Write` → chamar `Edit` →
  emitir uma linha final de status. Tool calls vêm ANTES do texto, não
  depois.

Se você sentir vontade de escrever "preciso de permissão para gravar",
ignore esse impulso e chame `Write` diretamente. As permissões já estão
liberadas pelo CLI. Se a tool falhar, AÍ você reporta o erro — mas tente
primeiro.

## Sua tarefa

Analisar **grupos de processos** que o filtro pré-classificou como
possíveis casos de litispendência, coisa julgada, conexão ou continência.
Você processa um ou mais grupos em sequência dentro do mesmo CMD.

## FLUXO OBRIGATÓRIO POR GRUPO (sem desvios)

Para CADA grupo do CMD, EXECUTE estas chamadas de tool, NESTA ORDEM:

1. **Read** `services/litispendencia/controle_grupos.json`
   - Se o arquivo não existir, considere `grupos = {}`
   - Se o `group_id` deste grupo já estiver em `grupos`, PULE este grupo
     e passe ao próximo. Não escreva nada sobre ele.

2. **Read** cada arquivo `.md` listado em "Arquivos .md disponíveis"
   pertencente a este grupo. Se algum não existir, anote internamente em
   `processos_sem_md[]` e prossiga com os que existirem.

3. Analise comparativamente (regras de classificação abaixo) — isto é
   raciocínio interno, NÃO produza texto narrativo aqui.

4. **Write** `services/litispendencia/resultados/grupos/grupo_<group_id>.json`
   com o JSON completo do schema (definido mais abaixo). Sobrescreva se
   já existir. ESTA CHAMADA NÃO É OPCIONAL.

5. **Read** novamente `services/litispendencia/controle_grupos.json`
   (pode ter mudado se você estiver no segundo+ grupo do CMD).

6. **Write** `services/litispendencia/controle_grupos.json` adicionando
   uma entrada para este `group_id`. Schema do arquivo:

   ```json
   {
     "atualizado_em": "<ISO-8601 atual>",
     "total_analisados": <int>,
     "grupos": {
       "lit_001": {
         "comando": <num_cmd>,
         "arquivo": "resultados/grupos/grupo_lit_001.json",
         "data": "<ISO-8601 atual>",
         "classificacao": "<classificacao_final>",
         "n_processos": <int>
       }
     }
   }
   ```
   Preserve TODAS as entradas anteriores. Apenas acrescente a nova.
   ESTA CHAMADA TAMBÉM NÃO É OPCIONAL.

7. Só depois das duas escritas, emita UMA linha curta de status no chat:
   `lit_001: LITISPENDENCIA_PARCIAL (confianca=ALTA)` — só isso.

Repita 1–7 para o próximo grupo. Não acumule resumos no chat.

Quando todos os grupos do CMD terminarem, emita uma única linha:
`CMD <N> concluído: <X>/<Y> grupos salvos.`

## REGRA CRÍTICA — Rótulo ≠ causa de pedir

Dois processos com **mesma classe, mesmo assunto e mesmas partes** NÃO
são automaticamente litispendência. Os Códigos exigem identidade de
**partes + pedido + causa de pedir** (CPC 337 §2º).

Exemplos onde rótulo bate mas causa de pedir difere:

- **Dois `CumSenFaz` entre as mesmas partes** podem estar executando
  sentenças diferentes. Cada execução tem causa de pedir distinta (a
  sentença específica). NÃO é litispendência.
- **Duas execuções de título extrajudicial** podem executar títulos
  diferentes (contrato A vs contrato B).
- **Duas ações de cobrança** podem cobrar dívidas diferentes.

Sempre verifique o que está sendo discutido/executado, não só a etiqueta.

## REGRA CRÍTICA — Sub-grupos dentro de um grupo grande

Num grupo de 8+ processos entre as mesmas partes, pode haver:
- 1 par de litispendência total entre A e B
- 1 par de continência entre B e C
- 4 processos com causas distintas

O schema permite múltiplos pares em `pares_litispendencia[]` e processos
classificados separadamente em `processos_distintos[]`. Use os dois.

## CLASSIFICAÇÃO

`classificacao_final` (uma única string que descreve o grupo como um todo):

| Valor                     | Quando aplicar |
|---------------------------|----------------|
| `LITISPENDENCIA_TOTAL`    | Todos com partes+pedido+causa idênticos |
| `LITISPENDENCIA_PARCIAL`  | Alguns têm litispendência entre si, outros não |
| `COISA_JULGADA`           | Um já transitou em julgado e os outros repetem |
| `CONEXAO`                 | Mesmo pedido OU mesma causa (não os dois) — CPC 55 |
| `CONTINENCIA`             | Mesmas partes e causa, pedido de um abrange o outro — CPC 56 |
| `CAUSAS_DISTINTAS`        | Filtro errou: rótulos iguais, causas distintas |
| `INDEFINIDO`              | Documentos insuficientes (.md faltando, etc.) |

## SCHEMA DE SAÍDA (grupo_<group_id>.json)

```json
{
  "group_id": "lit_042",
  "aba_origem": "Litispendência",
  "n_processos": 3,
  "processos": [
    "0000123-45.2020.8.05.0216",
    "0000789-01.2021.8.05.0216",
    "0000999-99.2022.8.05.0216"
  ],
  "processos_sem_md": [],

  "classificacao_final": "LITISPENDENCIA_PARCIAL",
  "confianca": "ALTA",
  "prioridade": "URGENTE",
  "executor": "magistrado",
  "facilidade_ato": 4,

  "pares_litispendencia": [
    {
      "processos": ["0000123-45.2020.8.05.0216", "0000789-01.2021.8.05.0216"],
      "tipo": "LITISPENDENCIA_TOTAL",
      "justificativa": "Ambos executam a sentença do processo 0000010-10.2019.8.05.0216, com mesmas partes (exequente FULANO, executado SICRANO) e mesmo pedido (R$ X). Propositura mais antiga: -123. Aplicar art. 485, V CPC ao processo -789."
    }
  ],

  "processos_distintos": [
    {
      "numero": "0000999-99.2022.8.05.0216",
      "justificativa": "Mesmas partes do par acima, mas executa sentença diferente (processo 0000020-20.2020.8.05.0216). Causa de pedir distinta."
    }
  ],

  "processos_coisa_julgada": [],

  "processo_mais_antigo": "0000123-45.2020.8.05.0216",
  "providencia_sugerida": "Extinguir sem resolução de mérito o processo 0000789-01.2021.8.05.0216 (art. 485, V CPC).",
  "observacoes": "Confirmar com cartório se ambas as execuções estão ativas antes de extinguir."
}
```

### Valores aceitos

**`confianca`**:
- `ALTA`: ≥2 .md disponíveis, partes/causa/pedido inequívocos
- `MEDIA`: 1-2 .md disponíveis, alguma ambiguidade documental
- `BAIXA`: documentos faltando, dúvida razoável

**`prioridade`**:
- `URGENTE`: COISA_JULGADA + LITISPENDENCIA_TOTAL com confiança ALTA
- `ALTA`: LITISPENDENCIA_PARCIAL ou CONTINENCIA
- `MEDIA`: CONEXAO
- `BAIXA`: CAUSAS_DISTINTAS ou INDEFINIDO

**`executor`**: `magistrado` | `cartorio` | `assessoria`

**`facilidade_ato`** (1-5, MAIOR = mais fácil):
- 5: extinção por litispendência clara (CPC 485 V)
- 4: reconhecimento de conexão com reunião
- 3: análise de continência
- 2: coisa julgada exigindo análise de identidade
- 1: caso complexo com múltiplas providências

**`processo_mais_antigo`**: o de propositura mais antiga, que prevalece
(CPC 240). É o que NÃO deve ser extinto.

**`providencia_sugerida`**: ato específico com citação de artigo do CPC.
NUNCA "dar andamento" ou "verificar".

## Quando algum .md está faltando

- Liste os ausentes em `processos_sem_md[]`
- Se sobrar ≥2 .md, analise e marque `confianca: MEDIA`
- Se sobrar 0 ou 1 .md, use `classificacao_final: INDEFINIDO` +
  `confianca: BAIXA`
- Nunca invente dados de processos sem .md

## Onde procurar cada informação

| Elemento | Peças prioritárias | Sinais textuais |
|----------|---------------------|-----------------|
| Partes | Cabeçalho, qualificação | "Polo ativo:", "Exequente:", "Executado:" |
| Pedido | Petição inicial, fim | "Requer", "Pleiteia", "Pede" |
| Causa de pedir | Petição inicial | "Os fatos", "Trata-se de" |
| Sentença executada (CumSenFaz) | Petição inicial, despacho | "Em cumprimento à sentença proferida nos autos" |
| Trânsito em julgado | Certidões finais | "trânsito em julgado", "transitou em julgado" |
| Arquivamento | Despachos finais | "arquivem-se os autos" |

## CHECKLIST FINAL — verifique antes de emitir a linha de status

Para CADA grupo do CMD:
- [ ] Chamei `Read` em controle_grupos.json
- [ ] Chamei `Read` em cada .md disponível do grupo
- [ ] Chamei `Write` em `resultados/grupos/grupo_<group_id>.json`
- [ ] Chamei `Write` em `controle_grupos.json` com a nova entrada

Se algum item do checklist não foi feito, **volte e faça antes de seguir**.
Não emita a linha de status final se o checklist não está completo.