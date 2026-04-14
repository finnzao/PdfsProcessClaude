# Projeto de Análise de Processos Criminais — Vara Criminal de Rio Real (0216) — TJBA

## Engine de Extração
- **pymupdf4llm** (PyMuPDF + layout analysis + OCR automático)
- Limpeza de lixo PJe/Sinesp, classificação de peças, cache MD5
- Redução média ~45% nos tokens vs extração bruta

## Comandos

| Comando | O que faz |
|---------|-----------|
| `python run.py extrair` | PDFs → markdown otimizado |
| `python run.py analise fila` | Gera fila de análise jurídica |
| `python run.py analise analisar` | Inicia sessão Claude Code |
| `python run.py analise consolidar` | Relatório final |
| `python run.py cautelares fila` | Gera fila de custodiados |
| `python run.py cautelares consolidar` | Planilha .xlsx |
| `python run.py status` | Status geral |
