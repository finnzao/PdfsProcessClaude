# Pipeline de Extração de Custodiados — Vara Criminal de Rio Real

Pipeline automatizado que usa o **Claude Code** para ler markdowns de processos
criminais e extrair dados dos custodiados (réus com cautelar de comparecimento
periódico — Art. 319, I CPP) para cadastro no sistema ACLP.

---

## Sumário

1. [Workflow em 3 comandos](#workflow-em-3-comandos)
2. [Como funciona](#como-funciona)
3. [Comandos detalhados](#comandos-detalhados)
4. [Arquivos gerados](#arquivos-gerados)
5. [Tratamento de rate limit](#tratamento-de-rate-limit)
6. [Salvamento incremental e retomada](#salvamento-incremental-e-retomada)
7. [Planilha final](#planilha-final)
8. [Solução de problemas](#solução-de-problemas)

---

## Workflow em 3 comandos

```bash
# 1. Gera fila de comandos (lote de 2 processos cada)
python run.py cautelares fila-extracao

# 2. Roda batch — Claude Code lê os markdowns e extrai os dados
python auto_extrair_cautelares.py --consolidar

# 3. (Opcional, já incluído no --consolidar do passo 2) Gera planilha xlsx
python run.py cautelares consolidar-extracao
```

**Atalho:** o `--consolidar` no passo 2 já gera a planilha automaticamente ao
final, então você só precisa de **2 comandos** na prática.

---

## Como funciona

```
textos_extraidos/*.md
        │
        ▼  (1) Gera fila ignorando processos já extraídos
fila_extracao.json + comandos_extracao.txt
        │
        ▼  (2) Claude Code roda em batch (incremental + retry de rate limit)
resultados/extracao/extracao_NNN.json   ← append a cada processo
processos_claude_code.json              ← append a cada processo
        │
        ▼  (3) Consolida todos os JSONs e gera planilha
result/cautelares_get_info/custodiados_cadastro.xlsx
```

Cada CMD processa **2 processos** por vez. O Claude Code:
1. Lê o `processos_claude_code.json` para saber quais processos já foram feitos
2. Para cada `.md` na lista, extrai os dados do(s) réu(s)
3. **Salva imediatamente** no `extracao_NNN.json` após cada processo
4. **Atualiza** o `processos_claude_code.json` com o número do processo
5. Só então passa para o próximo `.md`

---

## Comandos detalhados

### `python run.py cautelares fila-extracao`

**O que faz:** Lê todos os `.md` em `textos_extraidos/`, ignora os processos que
já estão em `processos_claude_code.json`, e gera comandos em batches de 2.

**Saída:**
- `services/cautelares_get_info/fila_extracao.json` — metadados da fila
- `services/cautelares_get_info/comandos_extracao.txt` — comandos prontos

**Exemplo:**
```bash
$ python run.py cautelares fila-extracao
  Markdowns encontrados:    53
  Já extraídos (controle):  2
  Pendentes a processar:    51
  ✓ Fila gerada
  Total: 26 comandos com até 2 processos cada
```

**Filtros opcionais:**
```bash
# Filtra por prefixo do número do processo
python run.py cautelares fila-extracao -- --filtro=8001

# Reprocessa TUDO (mesmo já extraídos)
python run.py cautelares fila-extracao -- --forcar

# Usa pasta diferente de textos_extraidos
python run.py cautelares fila-extracao -- /caminho/outra/pasta
```

---

### `python auto_extrair_cautelares.py`

**O que faz:** Executa os comandos da fila em sequência via Claude Code CLI.

**Comportamento:**
- Pula CMDs cujos processos já estão todos no controle global
- Detecta rate limit e espera o reset automaticamente
- Salva log de cada CMD em `services/cautelares_get_info/logs/cmd_NNN.log`
- Tenta até 3 vezes em caso de erro (configurável)
- Pode ser interrompido com Ctrl+C — retoma de onde parou

**Saída padrão (sem flags):**
```bash
============================================================
  CMD 001 | 2 processos no batch
  0000101-29.2018.8.05.0216, 0000114-96.2016.8.05.0216
============================================================
  ✓ OK em 2m13s | todos os 2 processos extraídos
  ✓ Checkpoint: CMD #001 concluído | Total geral: 2 processos extraídos
```

**Flags úteis:**

| Flag | O que faz |
|---|---|
| `--max N` | Roda só os primeiros N comandos (útil para teste) |
| `--de N` | Começa do comando N |
| `--ate N` | Para no comando N |
| `--dry` | Preview — mostra o que seria feito sem executar |
| `--verbose` | Mostra a saída do Claude em tempo real |
| `--consolidar` | Gera a planilha xlsx ao final |
| `--pausa N` | Segundos de pausa entre comandos (padrão: 5) |
| `--timeout N` | Timeout por comando em segundos (padrão: 600 = 10min) |
| `--max-tentativas N` | Tentativas por CMD em caso de erro (padrão: 3) |
| `--continuar-em-erro` | Não para se um CMD falhar |

**Exemplos:**
```bash
# Teste com 1 comando, vendo a saída do Claude em tempo real
python auto_extrair_cautelares.py --max 1 --verbose

# Roda os comandos 5 a 10
python auto_extrair_cautelares.py --de 5 --ate 10

# Roda tudo e gera a planilha ao final
python auto_extrair_cautelares.py --consolidar

# Preview do que seria feito
python auto_extrair_cautelares.py --dry

# Roda mesmo com erros (não para)
python auto_extrair_cautelares.py --continuar-em-erro --consolidar
```

---

### `python run.py cautelares status-extracao`

**O que faz:** Mostra o progresso atual da extração.

**Pode ser rodado a qualquer momento**, inclusive enquanto o batch está
executando em outro terminal.

**Saída:**
```
  ── Status da extração ──
  [###############-------------------------] 38.5%
  Comandos:  10/27 concluídos | 1 parciais
  Processos: 20/53 extraídos
  Total geral no controle: 22 processos

  ── CMDs parciais (alguns processos faltam) ──
  CMD 011: 1 feitos / 1 pendentes

  Próximo CMD pendente: ~011
  Retomar com: python auto_extrair_cautelares.py
```

---

### `python run.py cautelares consolidar-extracao`

**O que faz:** Lê todos os `extracao_*.json`, valida os dados e gera a planilha
final em `result/cautelares_get_info/custodiados_cadastro.xlsx`.

**Pode ser rodado:**
- Após o batch terminar
- Em qualquer momento para gerar uma planilha parcial
- Várias vezes (sobrescreve a anterior)

**Saída:**
```
  Lendo: services/cautelares_get_info/resultados/extracao
  53 registros encontrados

  ── Resumo ──
  Total:      53
  ✓ PRONTO:    18  (importador consome direto)
  ⚠ REVISAR:   12  (humano analisa antes)
  ✗ BLOQUEADO: 23  (descartado)

  ✓ Planilha: result/cautelares_get_info/custodiados_cadastro.xlsx
```

---

### `python run.py cautelares marcar-extracao <NUM>`

**O que faz:** Marca manualmente um CMD como concluído.

**Quando usar:** Se você rodou um comando do Claude Code manualmente (fora do
auto-runner) e quer registrar isso no checkpoint.

```bash
python run.py cautelares marcar-extracao 5
```

---

### `python run.py cautelares reset-extracao`

**O que faz:** Limpa a fila e o checkpoint, mas **preserva**:
- Os JSONs em `resultados/extracao/`
- O `processos_claude_code.json` (controle global)

**Quando usar:** Quando você quer regenerar a fila com filtros diferentes ou
recomeçar o batch sem perder os dados já extraídos.

```bash
python run.py cautelares reset-extracao
```

---

### `python run.py cautelares limpar-controle`

**O que faz:** Zera o `processos_claude_code.json` (com backup automático).

⚠️ **Cuidado:** após isso, todos os processos vão ser considerados pendentes
de novo na próxima geração de fila.

```bash
# Mostra aviso e instruções
python run.py cautelares limpar-controle

# Confirma e executa (gera backup .bkp_YYYYMMDD_HHMMSS.json)
python run.py cautelares limpar-controle --confirmar
```

---

## Arquivos gerados

```
services/cautelares_get_info/
├── fila_extracao.json              ← metadados da fila atual
├── comandos_extracao.txt           ← comandos prontos para o Claude Code
├── checkpoint_extracao.json        ← progresso do batch (CMDs OK/parciais)
├── processos_claude_code.json      ← CONTROLE GLOBAL (granular por processo)
│
├── resultados/extracao/
│   ├── extracao_001.json           ← array de processos do CMD 001
│   ├── extracao_002.json           ← array de processos do CMD 002
│   └── ...
│
└── logs/
    ├── cmd_001.log                 ← stdout completo do Claude Code
    ├── cmd_001.prompt.txt          ← prompt enviado para o CMD 001
    └── ...
```

E na pasta `result/`:

```
result/cautelares_get_info/
└── custodiados_cadastro.xlsx       ← planilha final para cadastro
```

---

## Tratamento de rate limit

Quando você atinge o limite de tokens do plano Claude, o Claude Code retorna
mensagens como:

```
You've hit your limit · resets 1pm (America/Fortaleza)
```

O `auto_extrair_cautelares.py`:

1. **Detecta automaticamente** via regex (várias variantes suportadas)
2. **Calcula o tempo até o reset** respeitando o timezone informado
3. **Mostra contador regressivo** no terminal:
   ```
   ============================================================
     RATE LIMIT DETECTADO
   ============================================================
     Mensagem do Claude:   hit your limit · resets 1pm
     Aguardando até:       06/05/2026 13:00:30 -03
     Tempo total de espera: 75min 23s
     Comando interrompido: CMD 008
   ============================================================

     Aguardando rate limit reset...  74min 12s
   ```
4. **Espera até reset + 30s de margem**
5. **Retoma do mesmo CMD** automaticamente
6. **Não conta como tentativa falha** (rate limit é tratado separadamente)

Se a espera passar de 4h, ele avisa para você decidir se quer interromper com
Ctrl+C e retomar mais tarde.

---

## Salvamento incremental e retomada

### Como o progresso é preservado

O Claude Code é instruído a salvar **após cada processo**, não só no final do
CMD. Isso garante que mesmo se travar no meio:

**Cenário:** CMD 005 com 2 processos (A e B). Claude processa A, depois trava
no meio de B (rate limit / timeout / erro).

- ✅ `extracao_005.json` tem o objeto de A salvo
- ✅ `processos_claude_code.json` lista A como extraído
- ✅ B fica registrado como pendente

**Ao retomar com `python auto_extrair_cautelares.py`:**
- Runner detecta status **PARCIAL** no CMD 005 (1/2 feitos)
- Re-executa CMD 005, mas Claude pula A (já está no controle) e só processa B
- Append em `extracao_005.json` adiciona B sem duplicar A
- CMD marcado como concluído

### Granularidade

| Arquivo | Granularidade | Atualizado por |
|---|---|---|
| `processos_claude_code.json` | Por **processo** | Claude Code (a cada processo) |
| `checkpoint_extracao.json` | Por **CMD** | Runner (após CMD completo) |
| `extracao_NNN.json` | Por **CMD** (array) | Claude Code (append por processo) |

---

## Planilha final

Arquivo: `result/cautelares_get_info/custodiados_cadastro.xlsx`

Cada linha = 1 réu. A coluna **STATUS_CADASTRO** classifica em 3 cores:

| Status | Cor | Significado |
|---|---|---|
| 🟢 **PRONTO** | Verde | Todos os campos OK, importador consome direto |
| 🟡 **REVISAR** | Amarelo | Passa na validação mas tem pendências (telefone vazio, gaps em observações, cautelar SUSPEITA_ATIVA) |
| 🔴 **BLOQUEADO** | Vermelho | Falta CPF/RG, dado obrigatório ausente, ou cautelar EXTINTA — descartar |

### Validação aplicada

**Bloqueia (vai pra 🔴):**
- Sem `nome`
- Sem CPF nem RG
- Sem `processo`
- Sem `dataDecisao`
- Sem `periodicidade`
- Sem `cep`, `logradouro`, `bairro` ou `cidade`
- `estado` não é sigla UF de 2 letras
- Cautelar EXTINTA / NUNCA_IMPOSTA / CONVERTIDA_PREVENTIVA

**Marca como REVISAR (vai pra 🟡):**
- Cautelar SUSPEITA_ATIVA ou VERIFICAR
- Sem telefone (campo "Pendente")
- Sem CPF (só RG)
- Claude registrou observações com mais de 30 chars (sinal de gap)

### Colunas principais

| Coluna | Descrição |
|---|---|
| `STATUS_CADASTRO` | 🟢 PRONTO / 🟡 REVISAR / 🔴 BLOQUEADO |
| `MOTIVO_REVISAO` | Lista os problemas encontrados |
| `nome` | Nome completo do réu |
| `cpf` / `rg` | Documentos |
| `contato` | Telefone (ou "Pendente") |
| `processo` | Número CNJ do processo |
| `vara` / `comarca` | Vara Criminal de Rio Real |
| `dataDecisao` | Data da imposição da cautelar (yyyy-MM-dd) |
| `dataComparecimentoInicial` | Calculada (decisão + periodicidade) |
| `periodicidade` | Dias entre comparecimentos |
| `cep` → `estado` | Endereço completo |
| `observacoes` | **Texto livre do Claude** com gaps e fontes |
| `status_cautelar` | Diagnóstico (ATIVA, SUSPEITA_ATIVA, etc) |
| `peca_fonte` / `pagina_fonte` | Onde os dados foram localizados |

### Recursos da planilha

- **Filtro automático** no cabeçalho (ative com Ctrl+Shift+L se desligado)
- **Dropdowns de validação** nas colunas STATUS_CADASTRO e estado
- **Painel congelado** nas duas primeiras colunas (STATUS + MOTIVO)
- **Cores por grupo** no cabeçalho (operacional, pessoal, doc, processo, endereço, auxiliar)

---

## Solução de problemas

### "Claude Code não encontrado no PATH"

```bash
npm install -g @anthropic-ai/claude-code
claude login
```

### CMD falha rapidamente (< 30s) sem extrair nada

O runner agora mostra um **preview do log** automaticamente nesse caso. Veja
também o arquivo completo em `services/cautelares_get_info/logs/cmd_NNN.log`.

Causas comuns:
- Permissões de ferramentas — o runner usa `--permission-mode acceptEdits`
- Versão antiga do Claude Code — atualize com `npm update -g @anthropic-ai/claude-code`

### Quero refazer um CMD específico

```bash
# Apaga o JSON do CMD
rm services/cautelares_get_info/resultados/extracao/extracao_005.json

# Remove os processos desse CMD do controle global
# (edite manualmente o processos_claude_code.json para remover as entradas)

# Roda apenas esse CMD
python auto_extrair_cautelares.py --de 5 --ate 5
```

### Quero limpar tudo e recomeçar do zero

```bash
# 1. Faz backup do que já foi extraído (recomendado)
cp -r services/cautelares_get_info/resultados/extracao backup_extracao_$(date +%Y%m%d)

# 2. Reset do batch
python run.py cautelares reset-extracao

# 3. Limpa o controle global (com backup automático)
python run.py cautelares limpar-controle --confirmar

# 4. Apaga os JSONs (cuidado!)
rm services/cautelares_get_info/resultados/extracao/extracao_*.json

# 5. Recomeça
python run.py cautelares fila-extracao
python auto_extrair_cautelares.py --consolidar
```

### Bati rate limit e ele esperou demais

A espera é até o horário de reset informado pelo Claude. Se for muito longa
(>4h), o runner avisa e você pode dar Ctrl+C, esperar manualmente, e retomar
depois com `python auto_extrair_cautelares.py`.

### O Claude está extraindo dados errados (réu vs vítima)

Verifique o `prompt_extracao.md` em `services/cautelares_get_info/prompts/`. As
regras de identificação de papel processual estão lá. Você pode ajustar e
reprocessar os CMDs problemáticos.

---

## Estrutura completa do projeto

```
projeto/
├── auto_extrair_cautelares.py       ← runner com retry de rate limit
├── run.py                            ← CLI raiz (já existente)
└── services/cautelares_get_info/
    ├── main.py                       ← comandos do pipeline
    ├── prompts/
    │   ├── prompt_extracao.md        ← schema + regras (lido pelo Claude)
    │   └── prompt_custodiado.md      ← prompt antigo (mantido)
    ├── scripts/
    │   ├── fila_extracao.py          ← gera fila
    │   ├── consolidar_extracao.py    ← lê JSONs, valida, gera xlsx
    │   ├── pre_extracao.py           ← antigo (regex, mantido)
    │   └── consolidar.py             ← antigo (regex, mantido)
    ├── resultados/
    │   ├── extracao/                 ← JSONs extraídos pelo Claude
    │   └── (outros arquivos antigos)
    ├── logs/
    │   ├── cmd_NNN.log               ← stdout do Claude Code
    │   └── cmd_NNN.prompt.txt        ← prompt enviado
    ├── fila_extracao.json            ← gerado por fila-extracao
    ├── comandos_extracao.txt         ← gerado por fila-extracao
    ├── checkpoint_extracao.json      ← progresso por CMD
    └── processos_claude_code.json    ← controle global (granular)
```
