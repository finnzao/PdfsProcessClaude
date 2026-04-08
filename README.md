# Análise de Processos Criminais com Claude Code

## Pré-requisitos
```bash
npm install -g @anthropic-ai/claude-code         # Claude Code
sudo apt install tesseract-ocr tesseract-ocr-por  # OCR (se tiver páginas scaneadas)
pip install pdfplumber pypdf pytesseract           # Python
```

## Passo a Passo Completo

### 1. Coloque os PDFs na pasta
```
projeto_final/pdfs/
├── 0000770-14_2020_8_05_0216-xxxxx-processo.pdf
├── 8000994-73_2021_8_05_0216-xxxxx-processo.pdf
└── ...
```

### 2. Extraia os textos (rode uma vez)
```bash
cd projeto_final
python3 scripts/extrair_processos.py
```
Processa cada PDF: extrai texto, aplica OCR se necessário, remove rodapés PJe (-46% ruído), detecta peças (Denúncia, Sentença, Despacho...), salva `.txt` limpo com `[PÁG. X]`.

**Tempo**: ~1-2 min por PDF. Para 394 PDFs: ~3-6 horas (rode e vá fazer outra coisa).

### 3. Gere a fila de comandos
```bash
python3 scripts/analisar_processos.py
```
Cruza textos com CSV, calcula urgência, gera `comandos_claude_code.txt` com todos os comandos prontos e numerados.

### 4. Inicie sessão no Claude Code
```bash
python3 scripts/sessao.py inicio   # registra início
claude                              # abre o Claude Code
```

### 5. Cole os comandos um por vez
Abra `comandos_claude_code.txt`. Cada comando tem este formato:
```
# === COMANDO 001 === [APOrd] [3 com PDF] ===
# Processos: 0000770-14.2020.8.05.0216 ...
# Ao concluir: python3 scripts/marcar_concluido.py 1 0000770-14.2020.8.05.0216

Leia o prompt em prompts/prompt_APOrd.md.
Analise os processos (leia CADA .txt completo):
  - textos_extraidos/0000770_14_2020_8_05_0216.txt (...)
...
Salve em resultados/analise_001.csv
```

**Após cada comando concluído**, cole a linha "Ao concluir" no Claude Code:
```
python3 scripts/marcar_concluido.py 1 0000770-14.2020.8.05.0216
```
Isso salva o progresso no checkpoint.

### 6. Quando a sessão expirar

O Claude Code tem limite de uso. Quando expirar:

```bash
python3 scripts/sessao.py fim      # registra fim + mostra horário para voltar
```

Saída:
```
🔴 SESSÃO #1 ENCERRADA
   Duração: 2h15min
   Comandos nesta sessão: 12
   Último comando: #012

📋 PARA RETOMAR:
   Restam 16 comandos
   Próximo: COMANDO #013

⏰ O limite geralmente reseta em ~5 horas.
   Volte por volta das 18:30 para continuar.
```

### 7. Retomando após pausa
```bash
python3 scripts/analisar_processos.py --status    # ver onde parou
python3 scripts/sessao.py inicio                   # registrar nova sessão
claude                                              # abrir Claude Code
# colar COMANDO 013 em diante...
```

### 8. Consolidar resultados
Quando todos os comandos forem feitos:
```bash
python3 scripts/consolidar.py
```
Gera `relatorio_final.csv` (todos os processos, ordenados por urgência) e `resumo_estatisticas.txt`.

## Comandos de Referência Rápida

| Situação | Comando |
|----------|---------|
| Extrair PDFs | `python3 scripts/extrair_processos.py` |
| Gerar fila | `python3 scripts/analisar_processos.py` |
| Ver progresso | `python3 scripts/analisar_processos.py --status` |
| Recomeçar do zero | `python3 scripts/analisar_processos.py --reset` |
| Iniciar sessão | `python3 scripts/sessao.py inicio` |
| Encerrar sessão | `python3 scripts/sessao.py fim` |
| Painel de controle | `python3 scripts/sessao.py info` |
| Marcar concluído | `python3 scripts/marcar_concluido.py N PROC1 PROC2` |
| Consolidar | `python3 scripts/consolidar.py` |

## Estrutura do Projeto
```
projeto_final/
├── CLAUDE.md                ← Lido automaticamente pelo Claude Code
├── README.md                ← Este arquivo
├── pdfs/                    ← PDFs dos processos (você coloca aqui)
├── textos_extraidos/        ← .txt limpos (gerado pelo extrair)
├── prompts/                 ← Prompts jurídicos por classe
│   ├── prompt_APOrd.md      ← Ação Penal Ordinária
│   ├── prompt_IP.md         ← Inquérito Policial
│   ├── prompt_TCO.md        ← Termo Circunstanciado (JECrim)
│   ├── prompt_Juri.md       ← Tribunal do Júri
│   ├── prompt_APSum.md      ← Ação Penal Sumária
│   ├── prompt_APSumss.md    ← Ação Penal Sumaríssima
│   └── prompt_outros.md     ← BoOcCi, ExMeSo, ECA, etc.
├── scripts/
│   ├── extrair_processos.py ← Extrai texto dos PDFs
│   ├── analisar_processos.py ← Gera fila e comandos
│   ├── marcar_concluido.py  ← Checkpoint por comando
│   ├── sessao.py            ← Controle de sessão
│   └── consolidar.py        ← Junta resultados
├── resultados/              ← CSVs de análise (gerado pelo Claude Code)
├── checkpoint.json          ← Estado atual (gerado automaticamente)
├── fila_analise.json        ← Fila completa (gerado)
├── comandos_claude_code.txt ← Comandos prontos (gerado)
└── processos_crime_parados_mais_que_100_dias.csv
```

## Como Funciona a Economia de Tokens

| Camada | O que faz | Economia |
|--------|-----------|----------|
| Extração | Remove rodapés/cabeçalhos PJe | -46% por processo |
| Prompts separados | Carrega só conhecimento da classe | ~1.5k tokens vs ~6k (tudo junto) |
| Batches de 3 | 3 processos com PDF por comando | ~50k tokens por comando |
| CLAUDE.md enxuto | Regras gerais sem repetir legislação | ~1.2k tokens fixos |
| **Total por comando** | | **~55k tokens (cabe em 200k)** |
