# Projeto de Análise de Processos Criminais — Vara Criminal de Rio Real (0216) — TJBA

## Visão Geral
Sistema modular para análise de processos criminais parados há mais de 100 dias.
Cada "service" é uma missão independente que usa o Claude Code para analisar PDFs de processos.

## Estrutura do Projeto

```
projeto_processos/
│
├── CLAUDE.md                  ← Este arquivo (lido automaticamente)
├── README.md                  ← Instruções de uso
├── run.py                     ← CLI unificado para todas as missões
│
├── pdfs/                      ← PDFs dos processos (ENTRADA ÚNICA)
├── textos_extraidos/          ← Textos extraídos dos PDFs (COMPARTILHADO)
├── files/                     ← Arquivos auxiliares (CSVs, planilhas)
│   └── processos_crime_parados_mais_que_100_dias.csv
│
├── common/                    ← Código compartilhado (DRY)
│   ├── __init__.py
│   ├── extrair_processos.py   ← Extração de PDFs → texto (roda 1x)
│   ├── sessao.py              ← Controle de sessão Claude Code
│   ├── checkpoint.py          ← Marcar progresso (genérico)
│   ├── fila_base.py           ← Classe base para geração de filas
│   ├── consolidar_base.py     ← Classe base para consolidação
│   └── utils.py               ← Utilitários compartilhados
│
├── services/                  ← Cada service = 1 missão independente
│   ├── analisar_processo/     ← MISSÃO 1: Análise jurídica
│   │   ├── __init__.py
│   │   ├── main.py            ← Lógica específica desta missão
│   │   ├── prompts/           ← Skills/prompts do Claude Code
│   │   ├── scripts/           ← Fila, consolidar (usam common/)
│   │   └── resultados/        ← CSVs gerados pelo Claude Code
│   │
│   └── cautelares_get_info/   ← MISSÃO 2: Extração de custodiados
│       ├── __init__.py
│       ├── main.py            ← Lógica específica desta missão
│       ├── prompts/           ← Skill do Claude Code p/ custodiados
│       ├── scripts/           ← Fila, consolidar (usam common/)
│       └── resultados/        ← JSONs gerados pelo Claude Code
│
└── result/                    ← Saídas finais de cada missão
    ├── analisar_processo/     ← relatorio_final.csv
    └── cautelares_get_info/   ← custodiados.xlsx
```

## Princípios

### DRY (Don't Repeat Yourself)
- `common/` contém TODO código reutilizável
- Services IMPORTAM de common/, nunca copiam
- Extração de PDFs roda 1 vez, ambos services leem de `textos_extraidos/`

### Separação de Responsabilidades
- Cada service tem seus próprios: prompts, scripts de fila, resultados, checkpoint
- `common/` NÃO contém lógica de negócio específica de nenhuma missão
- `result/` separa saídas finais por service

### Fluxo Padrão de Todo Service
1. Extração (comum): `python run.py extrair`
2. Gerar fila: `python run.py <service> fila`
3. Sessão: `python run.py <service> analisar`
4. Consolidar: `python run.py <service> consolidar`

## Comandos Rápidos

| Comando | O que faz |
|---------|-----------|
| `python run.py extrair` | Extrai PDFs → textos (1x, compartilhado) |
| `python run.py analise fila` | Gera fila da missão de análise jurídica |
| `python run.py analise analisar` | Abre sessão Claude Code p/ análise |
| `python run.py analise status` | Progresso da análise |
| `python run.py analise consolidar` | Gera relatório final |
| `python run.py cautelares fila` | Gera fila da missão de custodiados |
| `python run.py cautelares analisar` | Abre sessão Claude Code p/ custodiados |
| `python run.py cautelares status` | Progresso dos custodiados |
| `python run.py cautelares consolidar` | Gera planilha .xlsx |
