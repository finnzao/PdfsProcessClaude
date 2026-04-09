# Projeto de Análise de Processos Criminais

## Vara Criminal de Rio Real (0216) — TJBA

Sistema modular com duas missões independentes que compartilham a mesma base de PDFs extraídos.

## Pré-requisitos

```bash
pip install pdfplumber pypdf openpyxl
# OCR (opcional, só se tiver páginas escaneadas):
sudo apt install tesseract-ocr tesseract-ocr-por
pip install pytesseract Pillow PyMuPDF
```

## Fluxo Rápido

```bash
# 1. Coloque PDFs em pdfs/
# 2. Extraia textos (roda 1x, serve ambas missões)
python run.py extrair

# 3a. MISSÃO 1 — Análise Jurídica
python run.py analise fila
python run.py analise analisar      # abre sessão, cole comandos no Claude Code
python run.py analise marcar 1 0000770-14.2020.8.05.0216
python run.py analise consolidar    # gera result/analisar_processo/relatorio_final.csv

# 3b. MISSÃO 2 — Cadastro de Custodiados
python run.py cautelares fila
python run.py cautelares analisar
python run.py cautelares marcar 1 0000770-14.2020.8.05.0216
python run.py cautelares consolidar # gera result/cautelares_get_info/custodiados_para_cadastro.xlsx
```

## Comandos Disponíveis

| Comando | O que faz |
|---------|-----------|
| `python run.py extrair` | Extrai PDFs → textos (1x) |
| `python run.py status` | Status geral de tudo |
| `python run.py <service> fila` | Gera fila de comandos |
| `python run.py <service> status` | Progresso do service |
| `python run.py <service> analisar` | Inicia sessão Claude Code |
| `python run.py <service> pausa` | Registra pausa |
| `python run.py <service> marcar N PROC...` | Marca comando concluído |
| `python run.py <service> consolidar` | Gera relatório/planilha final |
| `python run.py <service> reset` | Recomeça do zero |

Services disponíveis: `analise`, `cautelares`

## Estrutura

```
projeto_processos/
├── pdfs/                          ← PDFs (entrada única)
├── textos_extraidos/              ← Textos extraídos (compartilhado)
├── files/                         ← CSVs auxiliares
├── common/                        ← Código compartilhado (DRY)
│   ├── extrair_processos.py       ← Extração PDFs → markdown
│   ├── sessao.py                  ← Controle de sessão
│   ├── checkpoint.py              ← Marcar progresso
│   ├── fila_base.py               ← Classe base p/ filas
│   ├── consolidar_base.py         ← Classe base p/ consolidação
│   └── utils.py                   ← Utilitários
├── services/
│   ├── analisar_processo/         ← Missão 1: Análise jurídica
│   │   ├── main.py
│   │   ├── prompts/               ← APOrd, IP, TCO, Juri...
│   │   └── resultados/
│   └── cautelares_get_info/       ← Missão 2: Custodiados
│       ├── main.py
│       ├── prompts/               ← prompt_custodiado.md
│       └── resultados/
├── result/                        ← Saídas finais
│   ├── analisar_processo/
│   └── cautelares_get_info/
└── run.py                         ← CLI unificado
```
