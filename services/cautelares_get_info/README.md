# cautelares_get_info — Pipeline de Extracao de Custodiados

Servico responsavel por extrair informacoes detalhadas de custodiados/reus em processos com cautelares ativas, a partir dos arquivos markdown gerados em `pre_extraido/`.

## Fluxo

1. **Pre-extracao** (`scripts/pre_extracao.py`): identifica os processos com sinalizadores de cautelar ativa nos markdowns ja gerados.
2. **Fila** (`scripts/fila_extracao.py`): monta `fila_extracao.json` e `comandos_extracao.txt` para o Claude Code.
3. **Execucao** (`auto_extrair_cautelares.py` na raiz): roda os comandos via Claude Code com retry de rate limit.
4. **Consolidacao** (`scripts/consolidar_extracao.py`): consolida `resultados/extracao/extracao_NNN.json` em planilha xlsx.

## Estrutura

```
cautelares_get_info/
├── README.md
├── README_extracao.md         # detalhamento do processo de extracao
├── __init__.py
├── main.py
├── prompts/
│   ├── prompt_custodiado.md          # extracao por Claude Code
│   ├── prompt_custodiado_revisor.md  # revisao de qualidade
│   └── prompt_extracao.md            # prompt-orquestrador
├── scripts/
│   ├── __init__.py
│   ├── consolidar.py
│   ├── consolidar_extracao.py
│   ├── fila_extracao.py
│   ├── main.py
│   ├── pre_extracao.py
│   └── tests/
│       ├── __init__.py
│       ├── test_consolidador.py
│       └── test_extratores.py
├── logs/                       # logs do Claude Code (cmd_NNN.log)
└── resultados/
    └── extracao/               # extracao_NNN.json gerados pelo Claude
```

## Controle de progresso

- `processos_claude_code.json` (controle global): chave por numero do processo, valor com dados extraidos.
- `checkpoint_extracao.json`: ultimo CMD concluido e parciais.
- O Claude Code salva incrementalmente apos cada processo, evitando reprocessamento em caso de timeout/rate-limit.
