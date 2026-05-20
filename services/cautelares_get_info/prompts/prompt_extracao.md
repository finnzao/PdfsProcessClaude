# Orquestrador de Extracao — Prompt Batch

Voce processara MULTIPLOS processos em sequencia. Para cada processo da lista abaixo:

1. LEIA o markdown correspondente em `pre_extraido/<numero>.md`.
2. APLIQUE as regras de extracao definidas em `services/cautelares_get_info/prompts/prompt_custodiado.md` (vide formato JSON la definido).
3. APENDE o resultado em `services/cautelares_get_info/processos_claude_code.json` (controle global) usando a chave `numero_processo`.
4. APENDE tambem em `services/cautelares_get_info/resultados/extracao/extracao_NNN.json` (array) — substitua NNN pelo numero deste batch.

## Regras criticas de salvamento

- SALVE INCREMENTALMENTE apos cada processo. Nao espere terminar todos. Isto e essencial para nao perder progresso em caso de timeout/rate-limit.
- ANTES de processar cada numero, verifique se ja existe em `processos_claude_code.json`. Se sim, PULE (idempotencia).
- Se `processos_claude_code.json` nao existir, crie com schema `{"atualizado_em": "...", "total_extraidos": 0, "processos": {}}`.
- Se `extracao_NNN.json` nao existir, crie com `[]` e va apendando.

## Schema do controle global

```json
{
  "atualizado_em": "ISO-8601",
  "total_extraidos": N,
  "processos": {
    "<numero>": {
      "extraido_em": "ISO-8601",
      "fonte_md": "pre_extraido/<numero>.md",
      ... (campos do prompt_custodiado.md) ...
    }
  }
}
```

## Tratamento de erros

- Se o markdown nao existir ou estiver vazio: NAO crie entrada; reporte ao usuario ao final do batch.
- Se a extracao falhar parcialmente para um processo: salve com `"alertas": ["motivo da falha"]` e continue para o proximo.

## Processos a extrair neste batch

(Listados abaixo no comando do auto_extrair_cautelares.py)
