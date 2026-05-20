# Detalhamento — Processo de Extracao via Claude Code

## Premissas

- O Claude Code roda localmente via CLI (`claude -p`), autenticado pelo `claude login`.
- A entrada e um prompt-batch contendo varios processos a serem extraidos em uma unica invocacao.
- Cada processo extraido e salvo IMEDIATAMENTE em `processos_claude_code.json` (controle global), permitindo retomada granular.

## Por que salvar incrementalmente?

- Rate limits, timeouts e interrupcoes nao causam perda de trabalho ja realizado.
- O `auto_extrair_cautelares.py` compara o que esta em `processos_claude_code.json` com a fila e re-executa apenas o que falta.

## Detector de rate limit

O orquestrador detecta na saida do Claude mensagens como:
> "You've hit your limit · resets 3pm (America/Bahia)"

Quando detectado, calcula o tempo de espera e aguarda automaticamente, retomando do mesmo CMD apos o reset.

## Schema do `processos_claude_code.json`

```json
{
  "atualizado_em": "ISO-8601",
  "total_extraidos": 0,
  "processos": {
    "<numero_processo_CNJ>": {
      "extraido_em": "ISO-8601",
      "fonte_md": "pre_extraido/NNN.md",
      "qualificacao": { ... },
      "cautelares": { ... },
      "fase_processual": "string",
      "alertas": ["lista"]
    }
  }
}
```

## Schema de `extracao_NNN.json`

Array contendo objetos no mesmo formato dos valores acima, agrupados pelo batch NNN.
