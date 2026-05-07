# Pipeline LLM para extração de custodiados

Pipeline novo onde o **Claude Code lê os markdowns extraídos** e gera os JSONs
estruturados, com **salvamento incremental** — não perde progresso se travar.

## Os dois arquivos de controle

```
services/cautelares_get_info/
├── processos_claude_code.json   ← controle GLOBAL (fonte da verdade)
└── checkpoint_extracao.json     ← controle do BATCH (CMDs feitos/parciais)
```

### `processos_claude_code.json` (GLOBAL)

Granularidade: **por processo**. Atualizado pelo Claude Code dentro de cada CMD,
após processar cada .md. É a fonte da verdade do que já foi extraído.

```json
{
  "atualizado_em": "2026-05-06T01:30:00",
  "total_extraidos": 42,
  "processos": {
    "8001234-56.2024.8.05.0216": {
      "comando": 1,
      "arquivo": "resultados/extracao/extracao_001.json",
      "data": "2026-05-06T01:25:00",
      "qtd_reus": 1
    }
  }
}
```

**Quando o gerador da fila e o runner consultam esse arquivo:**
- `fila-extracao`: ignora processos já listados (não inclui na fila)
- `auto_extrair_cautelares.py`: pula CMDs cujos processos estão todos listados
- Verificação pós-CMD: confere se cada processo do CMD está no controle

### `checkpoint_extracao.json` (BATCH)

Granularidade: **por CMD**. Registra CMDs concluídos, parciais (alguns processos
OK), e o ponteiro do último CMD executado.

## Como o salvamento incremental funciona

O prompt instrui o Claude a, para cada processo:

```
1. Ler processos_claude_code.json — pular se o processo já estiver lá
2. Extrair os dados do markdown
3. APPEND no resultados/extracao/extracao_NNN.json (cria array se não existir)
4. APPEND no processos_claude_code.json
5. Só ENTÃO ir ao próximo .md
```

**Resultado prático:**

Cenário: CMD 005 tem 2 processos (A e B). Claude processa A com sucesso, depois
trava no meio de B (rate limit, timeout, erro).

- `extracao_005.json` tem o objeto de A salvo
- `processos_claude_code.json` lista A como extraído
- Quando você retomar com `python auto_extrair_cautelares.py`:
  - Runner detecta que A já está no controle
  - Roda CMD 005 só para B
  - Claude pula A (vê que está em `processos_claude_code.json`) e só processa B
  - Append em `extracao_005.json` adiciona o objeto de B (não duplica A)
  - CMD 005 marcado como concluído

## Workflow

```
textos_extraidos/*.md
        │
        ▼  (1) gera fila ignorando os já em processos_claude_code.json
fila_extracao.json + comandos_extracao.txt
        │
        ▼  (2) Claude Code roda em batch (incremental + retry de rate limit)
resultados/extracao/extracao_NNN.json   ← append a cada processo
processos_claude_code.json              ← append a cada processo
        │
        ▼  (3) consolida e gera planilha
result/cautelares_get_info/custodiados_cadastro.xlsx
```

## Comandos

### Passo 1 — Gerar fila

```bash
python run.py cautelares fila-extracao
```

Lê `textos_extraidos/*.md`, ignora os processos já em
`processos_claude_code.json`, gera comandos em batches de **2 processos** cada.

```bash
python run.py cautelares fila-extracao -- --filtro=8001    # filtro por prefixo
python run.py cautelares fila-extracao -- --forcar         # ignora controle, refaz tudo
```

### Passo 2 — Rodar batch

```bash
python auto_extrair_cautelares.py
```

O runner:
1. Pula CMDs cujos processos estão todos no controle global
2. Para cada CMD pendente, mostra quantos já foram feitos vs faltam
3. Envia para `claude -p` (Claude Code CLI)
4. **Detecta rate limit** ("You've hit your limit · resets Xpm") → espera o reset
5. Verifica progresso via `processos_claude_code.json` (granular):
   - Todos OK → marca CMD concluído
   - Alguns OK → marca **PARCIAL**, retenta para os faltantes
   - Nenhum OK → marca erro, retenta com pausa
6. Mantém checkpoint para retomada

Flags úteis:
```bash
python auto_extrair_cautelares.py --max 10              # só 10 CMDs
python auto_extrair_cautelares.py --de 5 --ate 20       # CMDs 5 a 20
python auto_extrair_cautelares.py --dry                 # preview
python auto_extrair_cautelares.py --verbose             # output em tempo real
python auto_extrair_cautelares.py --consolidar          # gera planilha ao final
python auto_extrair_cautelares.py --max-tentativas 5    # mais tolerante
python auto_extrair_cautelares.py --continuar-em-erro   # não para em erro
```

### Passo 3 — Consolidar planilha

```bash
python run.py cautelares consolidar-extracao
```

Lê `resultados/extracao/extracao_*.json`, valida via `CadastroInicialDTO`,
gera xlsx em `result/cautelares_get_info/custodiados_cadastro.xlsx` com 3
status: 🟢 PRONTO, 🟡 REVISAR, 🔴 BLOQUEADO.

### Status e controle

```bash
python run.py cautelares status-extracao    # progresso granular (CMD + processo)
python run.py cautelares reset-extracao     # zera fila + checkpoint (NÃO apaga dados)
python run.py cautelares limpar-controle    # zera processos_claude_code.json (com backup)
```

## Tratamento de rate limit

Quando o Claude Code retorna mensagens como:

```
You've hit your limit · resets 1pm (America/Fortaleza)
```

O `auto_extrair_cautelares.py`:

1. Detecta automaticamente via regex
2. Calcula tempo até o reset (timezone-aware via `zoneinfo`)
3. **Se já tinha processos extraídos antes do rate limit, registra-os no
   checkpoint como parciais**
4. Mostra contador regressivo no terminal
5. Espera até reset + 30s de margem
6. Retoma — Claude pula processos já feitos via controle global

## Schema do JSON

`extracao_NNN.json` é um array. Para múltiplos réus no mesmo processo, gera
um objeto por réu:

```json
[
  {
    "numero_processo": "8001234-56.2024.8.05.0216",
    "nome": "JOAO DA SILVA",
    "cpf": "123.456.789-00", "rg": "12.345.678 SSP/BA",
    "telefone": "(75) 99999-1234",
    "cep": "48340-000", "logradouro": "Rua das Flores",
    "numero_endereco": "123", "bairro": "Centro",
    "cidade": "Rio Real", "estado": "BA",
    "status_cautelar": "ATIVA",
    "data_imposicao": "2024-03-15", "periodicidade_dias": 30,
    "peca_fonte": "AUDIENCIA_CUSTODIA", "pagina_fonte": "p.10-15",
    "multiplos_reus": false,
    "observacoes": "Telefone localizado no BO p.3..."
  }
]
```

## Estrutura de arquivos

```
projeto/
├── auto_extrair_cautelares.py          ← runner com retry de rate limit
├── run.py                              ← CLI raiz (já existente)
└── services/cautelares_get_info/
    ├── main.py                         ← novos comandos LLM
    ├── prompts/
    │   ├── prompt_extracao.md          ← schema novo + regras incrementais
    │   └── prompt_custodiado.md        ← antigo, mantido
    ├── scripts/
    │   ├── fila_extracao.py            ← gera fila (ignora já-extraídos)
    │   ├── consolidar_extracao.py      ← lê JSONs, gera xlsx
    │   └── (antigos, mantidos)
    ├── resultados/
    │   └── extracao/
    │       └── extracao_NNN.json       ← Claude faz append a cada processo
    ├── logs/
    │   └── cmd_NNN.log                 ← stdout do Claude por CMD
    ├── processos_claude_code.json      ← CONTROLE GLOBAL (granular)
    ├── fila_extracao.json              ← gerado por fila-extracao
    ├── comandos_extracao.txt           ← gerado por fila-extracao
    └── checkpoint_extracao.json        ← progresso do batch (CMDs)
```
