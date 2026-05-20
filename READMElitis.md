# Litispendência — Análise em lote via Claude Code

Pipeline de triagem automatizada de **litispendência** (CPC 337, § 1º–§ 3º),
**coisa julgada**, **conexão** e **continência** sobre processos cíveis já
agrupados pela planilha `litispendencia_2___1_.xlsx` (saída do script
`gerar_relatorios_litispendencia_1_.py`).

Segue a mesma arquitetura dos serviços `analisar_processo` e
`cautelares_get_info`, mas com **uma diferença essencial**: a unidade de
trabalho é o **grupo**, não o processo.

---

## Por que 1 grupo = 1 CMD?

Litispendência é uma análise **comparativa**: você só sabe se dois processos
são idênticos vendo-os lado a lado. Quebrar um grupo em batches diferentes
destruiria essa comparação.

Cada linha das abas `⭐ Litispendência` e `⚠ Coisa Julgada` da planilha vira
**um único CMD do Claude Code**, com todos os processos daquele grupo. Isso
traz três ganhos:

- **Retomada granular** — se travar no grupo 47, retoma do 47.
- **Prompt focado** — cada CMD vê só os 2-10 processos do seu grupo.
- **Custo previsível** — grupos pequenos viram CMDs baratos; só os grandes
  consomem mais tokens.

---

## Estrutura do kit

```
PDFSPROCESSCLAUDE/
├── auto_analisar_litispendencia.py          ← runner (Python, espelha auto_extrair_cautelares.py)
├── files/
│   └── litispendencia_2.xlsx                ← entrada (você precisa colocar aqui)
└── services/litispendencia/
    ├── prompts/
    │   └── prompt_litispendencia.md         ← o prompt jurídico
    ├── scripts/
    │   ├── fila_litispendencia.py           ← gera a fila a partir do xlsx
    │   └── consolidar_litispendencia.py     ← gera a planilha final
    ├── resultados/
    │   └── analises/                        ← um grupo_{ID}.json por grupo
    ├── logs/                                ← stderr/stdout do Claude por execução
    ├── fila_litispendencia.json             ← gerado pela fila
    ├── comandos_litispendencia.txt          ← gerado pela fila (legível)
    ├── controle_grupos.json                 ← fonte da verdade (grupos concluídos)
    └── checkpoint_litispendencia.json       ← retomada do batch
```

---

## Fluxo completo (3 comandos)

```bash
# 1. Coloca a planilha em files/litispendencia_2.xlsx
# 2. Gera a fila a partir das abas relevantes
python -m services.litispendencia.scripts.fila_litispendencia

# 3. Roda o batch + consolida ao final
python auto_analisar_litispendencia.py --consolidar
```

Saída final: `result/litispendencia/triagem_litispendencia.xlsx`.

---

## Os 3 scripts em detalhe

### `fila_litispendencia.py` — gera a fila

Lê o xlsx, extrai os grupos das abas pedidas, gera `fila_litispendencia.json`
+ `comandos_litispendencia.txt`. **Pula grupos já no `controle_grupos.json`**
(idempotente).

```bash
python -m services.litispendencia.scripts.fila_litispendencia [opções]
```

| Flag       | Default                       | O que faz |
|------------|-------------------------------|-----------|
| `--xlsx`   | `litispendencia.xlsx`         | Caminho da planilha de entrada |
| `--abas`   | `⭐ Litispendência,⚠ Coisa Julgada` | Quais abas processar (separadas por vírgula) |
| `--forcar` | off                           | Ignora `controle_grupos.json` e regenera tudo |

**IDs gerados:** `lit_001`, `cj_001`, `estrito_001` (prefixo conforme a aba).

---

### `auto_analisar_litispendencia.py` — runner

Executa cada CMD via `claude -p`, detecta rate limit, espera até reset,
verifica que o JSON foi gerado, e salva progresso por grupo. Roda apenas
grupos que ainda não estão em `controle_grupos.json`.

```bash
python auto_analisar_litispendencia.py [opções]
```

| Flag                    | Default | O que faz |
|-------------------------|---------|-----------|
| `--de N`                | 0       | Começa do CMD N (índice na fila) |
| `--ate N`               | 0       | Para no CMD N (0 = vai até o fim) |
| `--max N`               | 0       | Máximo de grupos nesta execução |
| `--dry`                 | off     | Preview: lista o que rodaria, sem chamar Claude |
| `--pausa S`             | 5       | Segundos entre grupos |
| `--timeout S`           | 600     | Timeout por grupo (Claude trava → mata e segue) |
| `--verbose`             | off     | Imprime stdout/stderr do Claude em tempo real |
| `--continuar-em-erro`   | off     | Não interrompe o batch quando um grupo falha |
| `--max-tentativas N`    | 3       | Retries por grupo (rate limit não conta) |
| `--consolidar`          | off     | Roda o consolidador ao final |

**Detecção de rate limit:** regex `hit your limit · resets Xpm` → calcula o
delta para o horário de reset (timezone-aware via `zoneinfo`) → dorme até lá
→ retoma sem perder a tentativa.

**Verificação pós-CMD:** confere que `grupo_{ID}.json` existe e contém os
campos obrigatórios (`classificacao_final`, `confianca`, `prioridade`). Se
faltar, marca como erro e retenta.

---

### `consolidar_litispendencia.py` — gera a planilha final

Lê todos os `grupo_*.json` em `resultados/analises/` e monta um xlsx com 4 abas:

```bash
python -m services.litispendencia.scripts.consolidar_litispendencia
```

Sem flags. Saída fixa em `result/litispendencia/triagem_litispendencia.xlsx`.

**Abas geradas:**

| Aba | Conteúdo |
|-----|----------|
| **Resumo por Grupo** | 1 linha por grupo, com coloração condicional (URGENTE/LIT_TOTAL em vermelho, COISA_JULGADA em vermelho-escuro, CONEXAO em amarelo, CAUSAS_DISTINTAS em verde). Ordenada por prioridade depois por tamanho do grupo. |
| **Pares Litispendência** | 1 linha por par identificado pela IA. `group_id` preservado em todas (rastreabilidade). |
| **Falsos Positivos** | Processos que o filtro agrupou mas que a IA classificou como `CAUSAS_DISTINTAS`, com justificativa. Use isso para refinar o filtro. |
| **Estatísticas** | Contadores por classificação, prioridade, confiança e aba de origem. |

---

## Schema do JSON por grupo

Cada `grupo_{ID}.json` em `resultados/analises/` tem esta forma:

```json
{
  "group_id": "lit_042",
  "aba_origem": "⭐ Litispendência",
  "classificacao_final": "LITISPENDENCIA_PARCIAL",
  "confianca": "ALTA",
  "prioridade": "URGENTE",
  "executor": "magistrado",
  "facilidade_ato": 4,
  "pares_litispendencia": [
    {
      "processos": ["0000123-45.2020.8.05.0216", "0000789-01.2021.8.05.0216"],
      "tipo": "LITISPENDENCIA_TOTAL",
      "justificativa": "Mesmas partes, mesma causa de pedir (execução da sentença do processo X), mesmo pedido."
    }
  ],
  "processos_distintos": [
    {
      "numero": "0000999-99.2022.8.05.0216",
      "justificativa": "Mesmas partes, mas executa sentença diferente."
    }
  ],
  "processos_coisa_julgada": [],
  "observacoes": "..."
}
```

**Classificações possíveis:**
`LITISPENDENCIA_TOTAL`, `LITISPENDENCIA_PARCIAL`, `COISA_JULGADA`, `CONEXAO`,
`CONTINENCIA`, `CAUSAS_DISTINTAS`, `INDEFINIDO`.

---

## Regras jurídicas chave no prompt

1. **Rótulo ≠ causa de pedir.** Dois `CumSenFaz` entre as mesmas partes podem
   estar executando sentenças diferentes. A IA é instruída a comparar **o
   que** está sendo executado/discutido, não só a classe processual.
2. **Sub-grupos dentro de um grupo grande.** Num grupo de 8 processos, pode
   haver 2 pares de litispendência + 4 distintos. O schema permite múltiplos
   `pares_litispendencia` — não força decisão binária.
3. **Documentos faltantes.** Se o `.md` de um processo não existe em
   `textos_extraidos/`, a IA registra como `INDEFINIDO` com confiança baixa,
   em vez de inventar.

---

## Pré-requisitos

```bash
pip install openpyxl
```

Claude Code instalado e configurado (mesmo setup dos outros services).

---

## Cenários de retomada

| Situação                                | O que fazer |
|-----------------------------------------|-------------|
| Travou no meio do batch                 | `python auto_analisar_litispendencia.py` — retoma de onde parou |
| Quero rodar só 10 grupos de teste       | `--max 10 --dry` para preview, depois sem `--dry` |
| Refiz o filtro, planilha mudou          | `--forcar` no `fila_litispendencia.py` regenera tudo |
| Quero re-analisar 1 grupo específico    | Apague `resultados/analises/grupo_{ID}.json` e a entrada em `controle_grupos.json`, depois rode o runner |
| Rate limit batendo direto               | Runner espera sozinho até o reset; sem ação manual |

---

## Integração com `run.py`

Este kit não inclui o `main.py` do service (para chamar via `python run.py
litispendencia ...`). Se quiser, é só pedir — é um arquivo pequeno seguindo
o padrão do `services/cautelares_get_info/main.py`.
