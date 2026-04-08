# Análise Jurídica de Processos Criminais — Vara Criminal de Rio Real (0216) — TJBA

## Visão Geral
394 processos criminais parados há mais de 100 dias. Os PDFs dos processos foram extraídos e convertidos em arquivos .txt na pasta `textos_extraidos/`, com texto limpo e referência de página.

## Estrutura do Projeto
```
├── CLAUDE.md              ← Este arquivo (lido automaticamente)
├── pdfs/                  ← PDFs originais dos processos
├── textos_extraidos/      ← Textos limpos extraídos dos PDFs (1 arquivo por processo)
├── prompts/               ← Prompts jurídicos por classe processual
│   ├── prompt_APOrd.md    ← Ação Penal Ordinária
│   ├── prompt_IP.md       ← Inquérito Policial
│   ├── prompt_TCO.md      ← Termo Circunstanciado
│   ├── prompt_Juri.md     ← Tribunal do Júri
│   ├── prompt_APSum.md    ← Ação Penal Sumária
│   ├── prompt_APSumss.md  ← Ação Penal Sumaríssima
│   └── prompt_outros.md   ← Demais classes
├── scripts/
│   ├── extrair_processos.py    ← Extrai texto dos PDFs (executar PRIMEIRO)
│   └── analisar_processos.py   ← Gera fila e comandos de análise
├── resultados/            ← Onde salvar as análises
├── fila_analise.json      ← Ordem otimizada de análise (gerado pelo script)
├── comandos_claude_code.txt ← Comandos prontos para copiar (gerado pelo script)
├── mapeamento_processos.json ← Mapa número→arquivo (gerado pelo script)
└── processos_crime_parados_mais_que_100_dias.csv ← Planilha original
```

## Fluxo de Trabalho

### Passo 1 — Extrair textos dos PDFs
```
python3 scripts/extrair_processos.py
```
Processa PDFs, aplica OCR se necessário, remove ruído do PJe, gera .txt limpos.

### Passo 2 — Gerar fila e comandos
```
python3 scripts/analisar_processos.py
```
Cruza textos com CSV, calcula urgência, gera `comandos_claude_code.txt` com comandos prontos.

### Passo 3 — Registrar início de sessão
```
python3 scripts/sessao.py inicio
```

### Passo 4 — Analisar processos
Abra `comandos_claude_code.txt` e cole os comandos no Claude Code, um por vez.
Após CADA comando concluído, marque no checkpoint:
```
python3 scripts/marcar_concluido.py <NUM> <PROCESSOS>
```
(o comando exato aparece no próprio texto de cada comando)

### Passo 5 — Se sessão expirar
```
python3 scripts/sessao.py fim                          # registra fim
python3 scripts/analisar_processos.py --status         # mostra onde parou
# ... esperar limite resetar ...
python3 scripts/sessao.py inicio                       # nova sessão
# retomar do comando indicado no --status
```

### Passo 6 — Consolidar resultados
```
python3 scripts/consolidar.py
```
Junta todos os CSVs de resultados/ em `relatorio_final.csv`.

## Scripts Disponíveis
| Script | Função |
|--------|--------|
| `scripts/extrair_processos.py` | Extrai texto dos PDFs (OCR + limpeza) |
| `scripts/analisar_processos.py` | Gera fila e comandos |
| `scripts/analisar_processos.py --status` | Mostra progresso atual |
| `scripts/analisar_processos.py --reset` | Recomeça do zero |
| `scripts/marcar_concluido.py N PROC...` | Marca comando como feito |
| `scripts/sessao.py inicio` | Registra início de sessão |
| `scripts/sessao.py fim` | Registra fim + horário p/ retomar |
| `scripts/sessao.py info` | Painel de controle completo |
| `scripts/consolidar.py` | Junta resultados em relatório final |

## Como Analisar um Processo

### Ao receber um comando de análise:
1. **Leia o prompt da classe** (ex: `prompts/prompt_IP.md`) — contém todo o conhecimento jurídico necessário
2. **Leia o .txt do processo** (ex: `textos_extraidos/0000770_14_2020_8_05_0216.txt`)
3. **Identifique**: fase processual, por que parou, risco de prescrição
4. **Gere a análise** no formato abaixo
5. **Cite páginas**: toda informação deve ter referência (ex: "conforme pág. 7")

### Formato de Saída (CSV)

| Coluna | Descrição |
|--------|-----------|
| numero | Número CNJ |
| classe | Classe processual |
| assunto | Crime/matéria |
| dias_parado | Dias sem movimentação |
| urgencia | CRITICA / ALTA / MEDIA / BAIXA |
| resumo_situacao | O que aconteceu (com ref. de páginas) |
| fase_processual | Em que fase está |
| diagnostico | Por que está parado |
| proximo_ato | Ação específica a tomar |
| modelo_despacho | Texto sugerido para despacho |
| fundamentacao_legal | Artigos de lei exatos |
| risco_prescricao | SIM / NAO / VERIFICAR + explicação |
| pecas_chave | Peças importantes com nº de página |
| observacoes | Alertas (preso, VD, hediondo, etc.) |
| id_acao | Identificador único (ACT-XXX) |

## Critérios de Urgência

| Nível | Critério |
|-------|----------|
| CRITICA | Dias > 730 OU Homicídio/Latrocínio/Estupro/Júri OU réu preso OU prescrição iminente |
| ALTA | Dias > 365 OU Tráfico/Roubo/Armas/VD OU vítima vulnerável |
| MEDIA | Dias 200-365 OU tarefa MINUTAR |
| BAIXA | Dias 100-200 sem agravantes |

**Regras de escalonamento**: VD → mínimo ALTA. Júri → mínimo ALTA. Estupro → mínimo ALTA. Prescrição iminente → CRITICA.

## Tabela de Prescrição (Art. 109 CP) — Referência Rápida

| Pena máxima | Prescrição | Crimes típicos |
|-------------|-----------|----------------|
| < 1 ano | 3 anos | Ameaça, contravenções |
| ≥ 1 e < 2 | 4 anos | Lesão leve, descumprimento MP |
| ≥ 2 e < 4 | 8 anos | Porte arma, receptação simples, furto simples |
| ≥ 4 e < 8 | 12 anos | Estelionato, furto qualificado, tráfico armas |
| ≥ 8 e < 12 | 16 anos | Roubo majorado, estupro |
| ≥ 12 | 20 anos | Homicídio, tráfico drogas, latrocínio |

## Qualidade Esperada
- NUNCA diga "dar andamento" — sempre especifique QUAL ato
- SEMPRE cite artigos de lei exatos
- SEMPRE sugira modelo de despacho com linguagem forense
- SEMPRE cite as páginas de onde extraiu informações
- SEMPRE avalie prescrição
