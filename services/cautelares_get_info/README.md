# services/cautelares_get_info — Cadastro de Custodiados

Vara Criminal de Rio Real (TJBA, Comarca 0216) — automação do cadastro
de comparecimento periódico no sistema (`CadastroInicialDTO`).

## Localização no projeto

```
PDFSPROCESSCLAUDE/
├── common/
│   └── reconciliador.py              ← genérico (papel ↔ PJe)
├── utils/
│   ├── tipos_pecas.py                ← classificação ponderada
│   ├── extrator_qualificacao.py      ← nome/CPF/RG/endereço
│   └── extrator_cautelar.py          ← status, periodicidade
├── services/
│   └── cautelares_get_info/          ← VOCÊ ESTÁ AQUI
│       ├── prompts/
│       │   └── prompt_custodiado_revisor.md
│       ├── resultados/               (saída do LLM revisor)
│       ├── scripts/
│       │   ├── main.py   ← CLI
│       │   ├── pre_extracao.py       ← markdown → JSON
│       │   ├── consolidar.py         ← JSON → xlsx
│       │   └── tests/
│       │       ├── test_extratores.py
│       │       └── test_consolidador.py
│       ├── README.md                 (este arquivo)
│       └── requirements.txt
├── files/                            (lista do papel + csv PJe)
├── textos_extraidos/                 (markdowns dos processos)
├── pre_extraido/                     (JSONs gerados)
└── result/                           (planilhas finais)
```

## Visão geral do pipeline

```
   Lista do papel + scc_info.csv
              │
              ▼
   ┌─────────────────────┐
   │ 1. Reconciliador    │   CNJ ↔ nome (fuzzy)
   │   common/           │
   └─────────┬───────────┘
             ▼
   ┌─────────────────────┐
   │ 2. Pré-extração     │   regex → JSON 70-85% pronto
   │   scripts/          │   sem chamar LLM
   └─────────┬───────────┘
             ▼
   ┌─────────────────────┐
   │ 3. (opcional) LLM   │   só revisa o que ficou ambíguo
   │   prompts/          │
   └─────────┬───────────┘
             ▼
   ┌─────────────────────┐
   │ 4. Consolidador     │   1 linha por processo
   │   scripts/          │   colunas alinhadas à DTO
   └─────────┬───────────┘
             ▼
        result/cadastro_inicial.xlsx
```

## Como rodar (a partir da raiz do projeto)

```bash
# Instalar dependências do serviço
pip install -r services/cautelares_get_info/requirements.txt

# Pipeline completo
python -m services.cautelares_get_info.scripts.main pipeline

# Ou comandos individuais
python -m services.cautelares_get_info.scripts.main reconciliar
python -m services.cautelares_get_info.scripts.main pre-extrair
python -m services.cautelares_get_info.scripts.main consolidar
```

## Saída final: `result/cadastro_inicial.xlsx`

Planilha de uma única aba alinhada 1:1 ao `CadastroInicialDTO`. Cada linha
é um cadastro inicial (custodiado + endereço + processo + 1º comparecimento).

| Coluna                      | Origem        | Obrig. DTO | Notas                              |
|-----------------------------|---------------|------------|------------------------------------|
| `STATUS_CADASTRO`           | calculado     | —          | PRONTO/REVISAR/BLOQUEADO (auxiliar)|
| `MOTIVO_REVISAO`            | calculado     | —          | texto livre (auxiliar)             |
| `nome`                      | regex+papel   | sim        | 2-150 chars                        |
| `contato`                   | regex         | não        | "Pendente" se ausente              |
| `cpf`                       | regex         | condic.    | formato `000.000.000-00`           |
| `rg`                        | regex         | condic.    | até 20 chars                       |
| `processo`                  | reconciliador | sim        | só dígitos, pontos e hífens        |
| `vara`                      | metadados     | sim        | até 100 chars                      |
| `comarca`                   | fixo          | sim        | "Rio Real"                         |
| `dataDecisao`               | regex         | sim        | ISO `yyyy-MM-dd`                   |
| `dataComparecimentoInicial` | calculado     | não        | dataDecisao + periodicidade        |
| `periodicidade`             | regex+map     | sim        | integer 1-365 (dias)               |
| `cep`                       | regex         | sim        | formato `00000-000`                |
| `logradouro`                | regex         | sim        | 5-200 chars                        |
| `numero`                    | regex         | não        | até 20 chars                       |
| `complemento`               | regex         | não        | até 100 chars                      |
| `bairro`                    | regex         | sim        | 2-100 chars                        |
| `cidade`                    | regex         | sim        | 2-100 chars                        |
| `estado`                    | regex         | sim        | sigla 2 letras                     |
| `observacoes`               | montado       | não        | peça-fonte + livro físico          |

## Regra `STATUS_CADASTRO`

| Status      | Quando | Importador faz |
|-------------|--------|----------------|
| `PRONTO`    | Todos os obrigatórios da DTO + cautelar `ATIVA`              | Importa direto |
| `REVISAR`   | DTO passa, mas há aviso (telefone "Pendente", `SUSPEITA_ATIVA`) | Humano analisa |
| `BLOQUEADO` | `isDocumentoValido()` falha OU cautelar EXTINTA/REVOGADA     | Não importa |

`isDocumentoValido()` é replicada localmente: **CPF ou RG é obrigatório**.

## Mapa de status da cautelar

| Status                  | Cadastrar? | Significado                                     |
|-------------------------|------------|-------------------------------------------------|
| `ATIVA`                 | SIM        | Imposta sem cessação posterior                  |
| `SUSPEITA_ATIVA`        | VERIFICAR  | Sursis/ANPP homologado sem prova de cumprimento |
| `INDEFINIDO`            | VERIFICAR  | Diagnóstico automático inconclusivo             |
| `AMBIGUA`               | VERIFICAR  | Sinais conflitantes                             |
| `NUNCA_IMPOSTA`         | VERIFICAR  | Sem peça de imposição localizada                |
| `EXTINTA_REVOGACAO`     | NÃO        | "Revogo as cautelares"                          |
| `EXTINTA_CUMPRIMENTO`   | NÃO        | "Cumprido o período de prova"                   |
| `EXTINTA_ABSOLVICAO`    | NÃO        | Absolvição com trânsito em julgado              |
| `EXTINTA_PUNIBILIDADE`  | NÃO        | "Declaro extinta a punibilidade"                |
| `CONVERTIDA_PREVENTIVA` | NÃO        | Cautelar virou preventiva                       |

## Inferência de `dataComparecimentoInicial`

Se o termo não fixar a data inicial explicitamente:

```
dataComparecimentoInicial = dataDecisao + periodicidade (dias)
```

Ex.: decisão 16/03/2024 + periodicidade 30 → primeira data 15/04/2024.

## Testes

```bash
# Da raiz do projeto
python -m services.cautelares_get_info.scripts.tests.test_extratores
python -m services.cautelares_get_info.scripts.tests.test_consolidador
```

Ambos rodam em segundos sem dependências externas além do `requirements.txt`.

## LLM revisor (etapa 3, opcional)

O prompt em `prompts/prompt_custodiado_revisor.md` orienta o Claude Code a
agir como **revisor**, não extrator. Ele recebe:

- O markdown do processo em `textos_extraidos/`
- O JSON pré-extraído em `pre_extraido/`

E deve salvar o resultado em `services/cautelares_get_info/resultados/`,
sobrescrevendo os JSONs antes da consolidação. O passo só é necessário se
você quiser que campos com `confianca: baixa` sejam revisados — o pipeline
funciona sem ele.

## Observação para o importador

Células vazias na planilha aparecem como `None` ao reler com openpyxl
(comportamento padrão do xlsx). O importador deve normalizar:

```python
import openpyxl
wb = openpyxl.load_workbook("result/cadastro_inicial.xlsx")
ws = wb["Cadastro"]

for row in ws.iter_rows(min_row=2, values_only=True):
    if row[0] != "PRONTO":            # STATUS_CADASTRO
        continue
    payload = {
        "nome":     row[2] or "",
        "contato":  row[3] or "Pendente",
        "cpf":      row[4] or None,
        "rg":       row[5] or None,
        # ...
    }
    api.cadastro_inicial(payload)
```
