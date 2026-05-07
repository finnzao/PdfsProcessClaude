# Extração de Custodiados — Vara Criminal de Rio Real

Você é um extrator de dados. Sua tarefa: ler o markdown de um processo
criminal e devolver um JSON com os dados do(s) réu(s) e da cautelar de
comparecimento periódico (Art. 319, I CPP).

## REGRA CRÍTICA — Salvar incrementalmente (NÃO PERDER PROGRESSO)

Você processa **vários processos em sequência** dentro do mesmo comando.
Para não perder trabalho se algo travar, você DEVE salvar o JSON depois
de CADA processo, não só no final.

### Fluxo obrigatório por processo

Para cada arquivo .md que receber:

1. **Verifique se já está em `processos_claude_code.json`** (controle global)
   - Caminho: `services/cautelares_get_info/processos_claude_code.json`
   - Se o `numero_processo` desse .md já estiver lá, PULE (já foi extraído antes)
   - Se não estiver, prossiga

2. **Leia e extraia os dados** do markdown conforme schema abaixo

3. **Faça APPEND no arquivo do comando**
   - Caminho: `services/cautelares_get_info/resultados/extracao/extracao_NNN.json`
   - Se NÃO existir, crie como `[]` e adicione o objeto
   - Se EXISTIR, leia o array, adicione o(s) novo(s) objeto(s), salve
   - Para processos com múltiplos réus, cada réu vira um objeto

4. **Atualize o controle global** `processos_claude_code.json`
   - Schema do controle:
     ```json
     {
       "atualizado_em": "2026-05-06T01:30:00",
       "total_extraidos": 42,
       "processos": {
         "8001234-56.2024.8.05.0216": {
           "comando": 1,
           "arquivo": "resultados/extracao/extracao_001.json",
           "data": "2026-05-06T01:25:00",
           "qtd_reus": 1
         }
       }
     }
     ```
   - Se não existir, crie a partir de `{"atualizado_em": "...", "total_extraidos": 0, "processos": {}}`
   - Adicione a entrada do `numero_processo` que você acabou de processar

5. **Só passe ao próximo .md depois desses 3 saves**

### Por que essa ordem importa

- Se o Claude Code travar no meio, o `extracao_NNN.json` continua válido
  com os processos já feitos (não perde nada)
- O `processos_claude_code.json` é o "ponteiro de retomada" — na próxima
  execução, processos já listados ali são pulados
- Se você for processar um arquivo cujo número já está no controle
  global, pule e diga "já extraído anteriormente" antes de seguir

## REGRA CRÍTICA — Diferenciar réu de vítima/testemunha

O markdown contém dados de várias pessoas (réu, vítima, testemunhas,
advogados). Você só extrai o RÉU. Confira o papel processual antes de
capturar qualquer dado.

Marcadores que identificam réu:
- "Réu:", "Réu(é):", "Acusado:", "Indiciado:", "Denunciado:", "Investigado:"
- "Qualificação do(a) acusado/indiciado/réu"
- "Custodiado:", "Conduzido:"

Marcadores que NÃO são do réu (NÃO capture esses dados):
- "Vítima:", "Ofendido(a):", "Qualificação da vítima"
- "Testemunha:", "Qualificação da testemunha"
- "Advogado:", "Defensor:", "Promotor:", "Juiz:"

Em caso de dúvida sobre o papel, deixe o campo vazio e registre em
`observacoes` que houve ambiguidade.

## REGRA CRÍTICA — Status da cautelar

Antes de marcar a cautelar como ativa, leia TODO o processo procurando:

### Foi imposta em algum momento?
Procure peças de imposição:
- Audiência de custódia (Art. 310 CPP)
- Decisão concedendo liberdade provisória (Art. 321 CPP)
- Cautelar do Art. 319 CPP
- Sursis processual homologado (Art. 89 Lei 9.099)
- ANPP homologado (Art. 28-A CPP)
- Termo de compromisso assinado pelo réu

Se NÃO encontrou imposição → `status_cautelar: NUNCA_IMPOSTA`

### Foi extinta posteriormente?
Procure decisões posteriores que cessam a cautelar:

| Sinal de extinção | Frase típica | Status |
|---|---|---|
| Sentença absolutória transitada | "absolvo o réu" + "transitou em julgado" | EXTINTA_ABSOLVICAO |
| Prescrição reconhecida | "extinta a punibilidade pela prescrição" | EXTINTA_PUNIBILIDADE |
| Sursis cumprido | "cumprido o período de prova", "Art. 89 §5º" | EXTINTA_CUMPRIMENTO |
| ANPP cumprido | "cumpridas as condições", "Art. 28-A §13" | EXTINTA_CUMPRIMENTO |
| Revogação expressa | "revogo as cautelares" | EXTINTA_REVOGACAO |
| Conversão em preventiva | "decreto a prisão preventiva" | CONVERTIDA_PREVENTIVA |
| Sentença condenatória transitada | "transitou em julgado" + "guia de execução" | EXTINTA_PUNIBILIDADE |

### A cautelar permanece ativa?
Se foi imposta E não foi extinta → `status_cautelar: ATIVA`

### Caso ambíguo
- Sursis/ANPP homologado mas sem certidão de cumprimento nos autos
  → `status_cautelar: SUSPEITA_ATIVA`
- Diagnóstico inconclusivo → `status_cautelar: VERIFICAR`

## SCHEMA DE SAÍDA

O arquivo `resultados/extracao/extracao_NNN.json` é um ARRAY de objetos.
Cada réu vira um objeto. Em concurso de réus, vários objetos com o mesmo
`numero_processo` e `multiplos_reus: true`.

```json
[
  {
    "numero_processo": "8001234-56.2024.8.05.0216",
    "classe": "APOrd",
    "assunto": "Roubo Majorado",
    "vara": "Vara Criminal de Rio Real",

    "nome": "JOAO DA SILVA SANTOS",
    "cpf": "123.456.789-00",
    "rg": "12.345.678 SSP/BA",
    "data_nascimento": "1990-05-15",
    "nome_mae": "MARIA DA SILVA",
    "nome_pai": "JOSE DA SILVA",
    "nacionalidade": "Brasileira",
    "estado_civil": "Solteiro",
    "profissao": "Pedreiro",

    "telefone": "(75) 99999-1234",

    "cep": "48340-000",
    "logradouro": "Rua das Flores",
    "numero_endereco": "123",
    "complemento": "Casa",
    "bairro": "Centro",
    "cidade": "Rio Real",
    "estado": "BA",

    "status_cautelar": "ATIVA",
    "data_imposicao": "2024-03-15",
    "periodicidade_dias": 30,
    "peca_fonte": "AUDIENCIA_CUSTODIA",
    "pagina_fonte": "p.10-15",
    "doc_id_fonte": "Num. 440867200",

    "reu_preso_atualmente": false,
    "multiplos_reus": false,

    "observacoes": "Telefone localizado no BO. Endereço único nos autos. Cautelar imposta em audiência de custódia, sem revogação posterior."
  }
]
```

## REGRAS DOS CAMPOS

### Documentos
- `cpf`: formato `000.000.000-00`. Se só houver dígitos, formate.
- `rg`: até 20 caracteres, com órgão expedidor se constar.
- **REGRA**: deve ter CPF OU RG. Se faltarem AMBOS, registre em
  `observacoes` que nenhum documento foi localizado.

### Datas
- `data_nascimento` e `data_imposicao`: formato ISO `yyyy-MM-dd`.
- Se ler "15/03/2024", converta para "2024-03-15".
- Se a data não constar, deixe string vazia `""`.

### Periodicidade
- `periodicidade_dias`: integer entre 1 e 365.
- Mapa: mensal=30, bimestral=60, quinzenal=15, semanal=7, trimestral=90.
- Se constar "a cada 45 dias", use 45.
- Se não constar, deixe `null`.

### Endereço

| Campo | Obrigatório | Regra |
|---|---|---|
| `cep` | **Sim** | Formato `00000-000` ou 8 dígitos |
| `logradouro` | **Sim** | Texto livre |
| `numero_endereco` | Não | Texto livre |
| `complemento` | Não | Texto livre |
| `bairro` | **Sim** | Texto livre |
| `cidade` | **Sim** | Texto livre |
| `estado` | **Sim** | **OBRIGATÓRIO em sigla UF de 2 letras maiúsculas** (ex: `BA`, `SP`, `RJ`, `MG`, `DF`). NUNCA escreva por extenso ("Bahia", "Rio de Janeiro") |

Regras práticas:
- Se for endereço de presídio/cadeia, marque `reu_preso_atualmente: true`
  e capture o endereço residencial em outro campo se houver.
- Se houver múltiplos endereços, use o MAIS RECENTE.
- Se faltar parte do endereço, deixe vazio (não invente) e registre em
  `observacoes` o que faltou.
- **Estado SEMPRE em sigla UF**: BA, SP, RJ, MG, DF, etc. Os 27 estados
  brasileiros têm sigla de 2 letras — use-as.

### Status da cautelar (valores permitidos)
- `ATIVA` — imposta e sem cessação posterior
- `SUSPEITA_ATIVA` — sursis/ANPP homologado sem prova de cumprimento
- `EXTINTA_REVOGACAO` — revogação expressa
- `EXTINTA_CUMPRIMENTO` — sursis/ANPP cumprido
- `EXTINTA_ABSOLVICAO` — absolvição com trânsito em julgado
- `EXTINTA_PUNIBILIDADE` — punibilidade declarada extinta
- `CONVERTIDA_PREVENTIVA` — virou preventiva
- `NUNCA_IMPOSTA` — sem peça de imposição localizada
- `VERIFICAR` — diagnóstico inconclusivo

### Múltiplos réus
Se o processo tiver mais de um réu, gere UM OBJETO POR RÉU no array,
todos com o mesmo `numero_processo`. Marque `multiplos_reus: true` em
todos eles. No `processos_claude_code.json`, registre `qtd_reus` com o
total.

### Observações (CAMPO MAIS IMPORTANTE)
Em `observacoes`, registre:
- Quais campos não foram localizados nos autos
- Onde você buscou cada dado (peça e página)
- Ambiguidades de papel processual
- Endereços alternativos encontrados
- Sinais de cumprimento parcial de sursis/ANPP
- Qualquer coisa que ajude o cartório a decidir o cadastro

Use linguagem direta. Exemplo:
> "CPF não localizado nos autos — só consta RG no BO p.3. Endereço
> divergente entre BO (Rua A, 123) e citação (Rua B, 456) — usei o mais
> recente da citação. Sursis processual homologado em 2022 sem certidão
> de cumprimento — verificar livro físico."

## ONDE PROCURAR CADA DADO

| Dado | Peças prioritárias | Sinais textuais |
|---|---|---|
| Nome completo | BO, qualificação, denúncia | "Qualificação:", "Réu:", "Acusado:" |
| CPF | Qualificação, BO | Formato 000.000.000-00 ou 11 dígitos |
| RG | BO, qualificação | "RG:", "documento de identidade" |
| Filiação | BO, qualificação, denúncia | "filho de", "mãe:", "pai:" |
| Data nascimento | BO, qualificação | "nascido em" |
| Endereço | BO, citação, denúncia | "residente em", "endereço:" |
| Telefone | BO, audiência, interrogatório | "telefone:", "celular:" |
| Cautelar imposta | Audiência custódia, decisões | "Art. 319", "comparecer" |
| Revogação | Decisões posteriores | "revogo", "extintas as cautelares" |

## REGRAS FINAIS

1. **Salve depois de CADA processo, não só no final** (ver regra crítica acima)
2. **Pule processos já listados em `processos_claude_code.json`**
3. **Um réu = um objeto JSON.** Em concurso, gere um objeto por réu.
4. **NUNCA invente dados.** Vazio é melhor que errado.
5. **Sempre cite peças e páginas em `observacoes`** quando localizar dados.
6. **Priorize informações recentes** sobre antigas.
7. **Use o cabeçalho `## SINALIZADORES PROCESSUAIS`** como ponto de
   partida, mas SEMPRE confirme no texto integral.
8. **Crie a pasta `extracao/`** se não existir antes de salvar.
