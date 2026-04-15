"""
formato_saida.py — Define o formato de saída que o Claude Code deve gerar.
Usado pelos geradores de comandos para incluir as instruções corretas.
"""

INSTRUCAO_SAIDA = """
## FORMATO DE SAIDA (OBRIGATORIO)

Para CADA processo, gere DOIS arquivos:

### 1. Ficha de triagem (JSON)
Salve em services/analisar_processo/resultados/triagem_{cmd}.json:

```json
[
  {{
    "numero": "0000000-00.2020.8.05.0216",
    "classe": "APOrd",
    "assunto": "Roubo Majorado",
    "dias_parado": 450,

    "fase_processual": "Alegacoes apresentadas, concluso para sentenca",
    "proximo_ato": "Minutar sentenca condenatoria/absolutoria",

    "urgencia_crime": "CRITICA",
    "risco_prescricao": "ATENCAO",
    "reu_preso": false,

    "executor": "Assessoria",
    "facilidade_ato": 1,

    "resumo": "Reu denunciado por roubo majorado com arma de fogo (Art. 157 §2o-A CP). AIJ realizada em 12/03/2023. Alegacoes finais de ambas as partes apresentadas. Processo concluso para sentenca desde 15/01/2024.",
    "fundamentacao_legal": "Art. 157 §2o-A CP. Pena 4-10a +2/3. Prescricao 20 anos. Ultimo marco: recebimento denuncia em 10/05/2021.",
    "pecas_chave": "Denuncia (p.3-5, Num. 440866922); AIJ (p.25-30, Num. 440867100); Alegacoes MP (p.35-38); Alegacoes Defesa (p.40-44)"
  }}
]
```

### Regras dos campos:

**urgencia_crime** (gravidade do tipo penal):
- CRITICA: homicidio, latrocinio, estupro, feminicidio, trafico
- ALTA: roubo, armas, VD com lesao, carcere privado
- MEDIA: furto qualificado, estelionato, receptacao, lesao leve
- BAIXA: ameaca, injuria, desobediencia, contravenções

**risco_prescricao**:
- PRESCRITO: prazo ja expirou
- IMINENTE: menos de 6 meses para prescrever
- ATENCAO: menos de 1 ano
- BAIXO: 1 a 3 anos
- SEM RISCO: mais de 3 anos

**executor** (quem faz o proximo ato):
- Cartorio: expedir citacao, intimar, certificar, remeter, abrir vista, expedir oficio/mandado/alvara
- Assessoria: minutar sentenca/decisao, reconhecer prescricao, homologar, analisar recebimento
- Externo: aguardar MP, delegado, laudo, carta precatoria
- Verificar: quando nao for claro

**facilidade_ato** (1 a 5, quanto MAIOR mais facil):
- 5: cartorio resolve sozinho (citar, intimar, certificar)
- 4: despacho padrao com modelo (arquivar, homologar, redesignar)
- 3: decisao com analise leve (receber denuncia, deferir MPU)
- 2: decisao com analise juridica (pronuncia, absolvicao sumaria)
- 1: trabalho pesado (minutar sentenca, decisao complexa)

**reu_preso**: true se o reu esta preso (preventiva ou temporaria). Verificar nos autos.

### 2. Analise completa (Markdown)
Salve em services/analisar_processo/resultados/analises/{{numero_arquivo}}.md

O nome do arquivo DEVE ser o numero do processo com _ no lugar de . e -
Exemplo: 0000770-14.2020.8.05.0216 -> 0000770_14_2020_8_05_0216.md

```markdown
# Analise — {{numero_processo}}

## Dados
| Campo | Valor |
|-------|-------|
| Classe | ... |
| Assunto | ... |
| Dias parado | ... |
| Urgencia | CRITICA / ALTA / MEDIA / BAIXA |
| Risco de prescricao | PRESCRITO / IMINENTE / ATENCAO / BAIXO / SEM RISCO |
| Executor do proximo ato | Cartorio / Assessoria / Externo |

## Situacao Atual
[O que aconteceu no processo ate agora, citando pecas e paginas]

## Fase Processual
[Fase exata: ex. "Instrucao encerrada, alegacoes apresentadas, concluso para sentenca"]

## Diagnostico
[Por que o processo esta parado e o que precisa ser feito]

## Proximo Ato
**Executor**: Cartorio / Assessoria / Externo
**Ato**: [descricao especifica — NUNCA "dar andamento"]
**Facilidade**: 1-5

## Prescricao
- Crime: [tipo] (Art. [X])
- Pena maxima: [X] anos
- Prazo prescricional: [X] anos (Art. 109, [inciso], CP)
- Ultimo marco interruptivo: [qual] em [data]
- Data limite: [data]
- Status: PRESCRITO / IMINENTE / ATENCAO / BAIXO / SEM RISCO
[Se menor de 21 na data do fato: prazo pela metade]

## Modelo de Despacho
```
[Texto COMPLETO do despacho pronto para o juiz assinar, adaptado ao caso concreto]
```

## Pecas-Chave
[Lista com paginas e IDs: "Denuncia (p.3-5, Num. XXXX)", etc.]

## Observacoes
[Alertas: nulidade, excesso de prazo, custodia, concurso de crimes, etc.]
```

### IMPORTANTE:
- Crie a pasta analises/ se nao existir
- O JSON de triagem deve ter um objeto por processo no array
- Cite SEMPRE paginas e pecas nos textos
- Proximo ato ESPECIFICO — nunca "dar andamento" ou "impulsionar"
- Calcule prescricao com datas reais dos autos
"""


def instrucao_para_comando(num_comando: int) -> str:
    """Retorna a instrução de saída formatada para um comando específico."""
    return INSTRUCAO_SAIDA.replace("{cmd}", f"{num_comando:03d}")
