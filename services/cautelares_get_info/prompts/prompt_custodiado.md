# Extração de Custodiados para Cadastro ACLP

Extrair dados pessoais de réus/custodiados para sistema de comparecimento.

## Extrair de CADA processo

### Dados Pessoais (obrigatórios)
- **nome**, **cpf** (000.000.000-00), **rg**, **contato** (telefone)
- ⚠️ CPF ou RG obrigatório. Sem nenhum → "NÃO ENCONTRADO — PREENCHER OBRIGATÓRIO"

### Endereço
- **logradouro**, **numero_endereco**, **complemento**, **bairro**
- **cidade** (default: Rio Real), **estado** (BA), **cep**

### Dados Processuais
- **processo** (CNJ), **vara** (Vara Criminal de Rio Real), **comarca** (Rio Real)

### Decisão de Comparecimento
- **precisa_comparecer**: SIM / NÃO / VERIFICAR
- **motivo_comparecimento**: explicação

NÃO comparecer: arquivado, absolvido, prescrito, sem cautelar, sursis sem comparecimento.
SIM comparecer: medida cautelar Art. 319 I, liberdade provisória, sursis penal Art. 78 §2º.
VERIFICAR: informação insuficiente ou ambígua.

### Campos Manuais
- **dataDecisao**, **periodicidade**, **dataComparecimentoInicial** → "PREENCHER MANUALMENTE"

## Onde Procurar
| Dado | Peça |
|------|------|
| Nome, CPF, RG | BO, qualificação, denúncia |
| Endereço | BO, citação, denúncia |
| Telefone | BO, audiência, interrogatório |
| Cautelar | Decisão, despacho, sentença |

## Saída JSON
```json
{"custodiados": [{"nome":"...","cpf":"...","rg":"...","contato":"...","processo":"...","vara":"Vara Criminal de Rio Real","comarca":"Rio Real","dataDecisao":"PREENCHER MANUALMENTE","periodicidade":"PREENCHER MANUALMENTE","dataComparecimentoInicial":"PREENCHER MANUALMENTE","cep":"...","logradouro":"...","numero_endereco":"...","complemento":"","bairro":"...","cidade":"Rio Real","estado":"BA","precisa_comparecer":"SIM","motivo_comparecimento":"...","observacoes":"..."}]}
```

Cite páginas. Múltiplos réus → um objeto cada. Dúvida → VERIFICAR.
