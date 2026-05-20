# Litispendência — Análise em lote (CPC 337)

Pipeline de triagem automatizada de **litispendência**, **coisa julgada**,
**conexão** e **continência** sobre processos cíveis já agrupados pelo seu
script `gerar_relatorios_litispendencia_1_.py`.

Segue o mesmo padrão dos outros services do projeto (`analisar_processo`,
`cautelares_get_info`): integra com `run.py`, usa `CheckpointManager` e
`SessaoManager` da `common/`, e tem runner separado na raiz.

---

## 🔧 Correção crítica do `services/__init__.py`

**Este pacote inclui um `services/__init__.py` corrigido**. O original
estava com imports do `cautelares_get_info` no nível do pacote, o que
quebra **qualquer** comando que toca `services.*` — não só o do
litispendência.

O novo `__init__.py` está vazio (só docstring), no padrão de pacotes
"guarda-chuva". Cada sub-service expõe suas funções por conta própria
no seu próprio `__init__.py`. Isso destrava todos os services.

---

## Decisões de design

### 1. Granularidade adaptativa (1 CMD ≠ 1 grupo, mas 1 grupo é a unidade)

Olhando a distribuição real dos grupos (110 com 2-3 procs, 6 com 6-10,
2 com 11+), 1 grupo por CMD desperdiçaria startup do `claude -p` 110 vezes
para análises leves. Mas botar grupos grandes juntos prejudicaria a
atenção do modelo na comparação dos pares.

A solução: **agrupar grupos consecutivos no mesmo CMD enquanto a soma de
processos ≤ 6; grupos com 6+ processos ficam isolados**. Resultado:
~50-55 CMDs em vez de 122, sem perder qualidade.

A **unidade de retomada continua sendo o grupo** (via `controle_grupos.json`).
Se o CMD trava no meio, o que já foi feito permanece registrado e na
próxima execução só os grupos faltantes do CMD são reprocessados.

### 2. Abas processadas por default

Apenas `⭐ Litispendência` e `⚠ Coisa Julgada` — as duas abas que seu
filtro pré-classificador identifica como mais relevantes (122 + 57 grupos).
As outras três (Estrito, Médio, Amplo) totalizam 1000+ grupos com muito
ruído e podem ser processadas via flag se quiser auditar.

### 3. Schema com sub-grupos

Litispendência num grupo grande raramente é binária. Pode haver 2 pares
de litispendência + 4 processos distintos. O schema permite:
- `pares_litispendencia[]` — múltiplos pares dentro do mesmo grupo
- `processos_distintos[]` — falsos positivos com justificativa
- `processos_coisa_julgada[]` — apartado para o caso da aba ⚠

### 4. Regras jurídicas embutidas no prompt

- **Rótulo ≠ causa de pedir** — dois CumSenFaz entre as mesmas partes
  podem executar sentenças diferentes
- **Processo mais antigo prevalece** (CPC 240) — identificado no JSON
- **Documentos faltantes** → `INDEFINIDO` com `confianca: BAIXA`, nunca
  inventa dados

---

## Estrutura

```
PDFSPROCESSCLAUDE/
├── auto_analisar_litispendencia.py     ← runner (espelha auto_extrair_cautelares.py)
├── services/
│   ├── __init__.py                     ← CORRIGIDO (sem imports)
│   └── litispendencia/
│       ├── __init__.py
│       ├── main.py                     ← integra com run.py
│       ├── prompts/
│       │   └── prompt_litispendencia.md
│       ├── scripts/
│       │   ├── __init__.py
│       │   ├── fila_litispendencia.py
│       │   └── consolidar_litispendencia.py
│       ├── resultados/grupos/          ← grupo_<id>.json (Claude escreve)
│       ├── logs/                       ← cmd_NNN.log do runner
│       ├── fila.json                   ← gerado por `fila`
│       ├── comandos_claude_code.txt    ← gerado por `fila`
│       ├── checkpoint.json             ← CheckpointManager padrão
│       └── controle_grupos.json        ← controle granular (estilo cautelares)
└── files/
    └── litispendencia.xlsx             ← entrada (renomeie sua planilha)
```

---

## Workflow

```bash
# 1. Renomeie sua planilha para files/litispendencia.xlsx
#    (ou passe --xlsx no comando fila)

# 2. Gere a fila
python run.py litispendencia fila

# 3. Rode o batch (com consolidação ao final)
python auto_analisar_litispendencia.py --consolidar

# Saída: result/litispendencia/triagem_litispendencia.xlsx
```

---

## Comandos do `run.py`

| Comando | O que faz |
|---------|-----------|
| `fila` | Gera `fila.json` + `comandos_claude_code.txt` a partir do xlsx |
| `status` | Mostra progresso (CMDs feitos vs total, grupos analisados) |
| `analisar` | Abre sessão de trabalho (`SessaoManager`) |
| `pausa` | Fecha sessão de trabalho |
| `marcar <N> <ids...>` | Marca CMD concluído manualmente |
| `consolidar` | Gera planilha xlsx final |
| `reset` | Limpa fila + checkpoint (preserva resultados e controle) |
| `limpar-controle` | Zera `controle_grupos.json` (com backup, requer `--confirmar`) |

### Flags do `fila`

```bash
python run.py litispendencia fila --xlsx=files/outra.xlsx
python run.py litispendencia fila --abas="⭐ Litispendência,⚠ Coisa Julgada,Filtro Estrito"
python run.py litispendencia fila --forcar    # ignora controle_grupos.json
```

### Flags do `auto_analisar_litispendencia.py`

| Flag | Default | O que faz |
|------|---------|-----------|
| `--de N` | 0 | Começa do CMD N |
| `--ate N` | 0 | Para no CMD N (0 = até o fim) |
| `--max N` | 0 | Máximo de CMDs nesta execução |
| `--dry` | off | Preview: lista o que rodaria sem chamar Claude |
| `--pausa S` | 5 | Segundos entre CMDs |
| `--timeout S` | 900 | Timeout por CMD |
| `--verbose` | off | Imprime stdout do Claude em tempo real |
| `--continuar-em-erro` | off | Não interrompe o batch quando um CMD falha |
| `--max-tentativas N` | 3 | Retries por CMD (rate limit não conta) |
| `--consolidar` | off | Roda o consolidador ao final |

---

## Schema do JSON por grupo

Cada `services/litispendencia/resultados/grupos/grupo_<id>.json`:

```json
{
  "group_id": "lit_042",
  "aba_origem": "⭐ Litispendência",
  "n_processos": 3,
  "processos": ["0000123-...", "0000789-...", "0000999-..."],
  "processos_sem_md": [],

  "classificacao_final": "LITISPENDENCIA_PARCIAL",
  "confianca": "ALTA",
  "prioridade": "URGENTE",
  "executor": "magistrado",
  "facilidade_ato": 4,

  "pares_litispendencia": [
    {
      "processos": ["0000123-...", "0000789-..."],
      "tipo": "LITISPENDENCIA_TOTAL",
      "justificativa": "Ambos executam a sentença do processo X..."
    }
  ],
  "processos_distintos": [
    {
      "numero": "0000999-...",
      "justificativa": "Mesmas partes, executa sentença diferente."
    }
  ],
  "processos_coisa_julgada": [],

  "processo_mais_antigo": "0000123-...",
  "providencia_sugerida": "Extinguir o processo -789 (CPC 485 V).",
  "observacoes": "..."
}
```

### Valores possíveis

**`classificacao_final`**: `LITISPENDENCIA_TOTAL`, `LITISPENDENCIA_PARCIAL`,
`COISA_JULGADA`, `CONEXAO`, `CONTINENCIA`, `CAUSAS_DISTINTAS`, `INDEFINIDO`.

**`confianca`**: `ALTA`, `MEDIA`, `BAIXA`.

**`prioridade`**: `URGENTE`, `ALTA`, `MEDIA`, `BAIXA`.

**`executor`**: `magistrado`, `cartorio`, `assessoria`.

**`facilidade_ato`**: 1 (complexo) a 5 (trivial).

---

## Planilha final (`triagem_litispendencia.xlsx`)

4 abas:

| Aba | Conteúdo |
|-----|----------|
| **Resumo por Grupo** | 1 linha por grupo, com coloração condicional. Ordenada por prioridade depois por tamanho do grupo |
| **Pares Litispendência** | 1 linha por par identificado. `group_id` preservado em todas (rastreabilidade) |
| **Falsos Positivos** | Processos que o filtro agrupou mas a IA classificou como distintos |
| **Estatísticas** | Contadores por classificação, prioridade, confiança e aba de origem |

---

## Tratamento de rate limit

Quando o Claude retorna `You've hit your limit · resets Xpm`, o runner:

1. Detecta via regex
2. Calcula o tempo até o reset (timezone `America/Fortaleza`)
3. Mostra contagem regressiva
4. Espera até reset + 30s
5. Retoma o CMD (sem contar como tentativa falha)
6. Claude pula grupos já feitos via `controle_grupos.json`

---

## Cenários de retomada

| Situação | O que fazer |
|----------|-------------|
| Travou no meio do batch | `python auto_analisar_litispendencia.py` — retoma do último CMD |
| Rate limit batendo direto | Runner espera sozinho |
| Refiz o filtro, planilha mudou | `python run.py litispendencia fila --forcar` |
| Re-analisar 1 grupo específico | Apague `resultados/grupos/grupo_<id>.json` e a entrada em `controle_grupos.json`, depois rode o runner |
| Auditar abas mais largas | `python run.py litispendencia fila --abas="Filtro Estrito"` |
| Quero rodar só 5 CMDs de teste | `python auto_analisar_litispendencia.py --max 5 --dry` (preview), depois sem `--dry` |

---

## Pré-requisitos

```bash
pip install openpyxl
```

Claude Code instalado e no PATH (mesmo setup dos outros services).

---

## O que NÃO está incluído

- **Integração com `run.py`**: pressuponho que seu `run.py` já tem o
  dispatcher genérico (`python run.py <service> <comando>` → chama
  `services/<service>/main.py:executar(comando, args)`). Como você usa
  esse padrão nos outros services, o de litispendência se encaixa
  automaticamente.

Se seu `run.py` precisar de uma entrada explícita para `litispendencia`,
me avise que mando o trecho de código.
