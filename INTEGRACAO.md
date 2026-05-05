# Integração ao PDFSPROCESSCLAUDE

Descompacte por cima da raiz do `PDFSPROCESSCLAUDE`. O zip contém arquivos
novos e **um arquivo que será sobrescrito**: `services/cautelares_get_info/scripts/main.py`.

## Resumo das mudanças

| Path | Ação | Observação |
|---|---|---|
| `requirements.txt` | merge ou cria | adicione as 3 deps na raiz |
| `common/reconciliador.py` | novo | |
| `common/__init__.py` | merge | exporta `Reconciliador` |
| `utils/tipos_pecas.py` | novo | classificação de peças |
| `utils/extrator_qualificacao.py` | novo | dados do réu |
| `utils/extrator_cautelar.py` | novo | status, periodicidade |
| `utils/__init__.py` | merge | re-exporta os utilitários |
| `services/__init__.py` | provavelmente já existe | mantenha o seu se houver |
| `services/cautelares_get_info/__init__.py` | merge | |
| `services/cautelares_get_info/README.md` | substitui | documentação atualizada |
| `services/cautelares_get_info/prompts/prompt_custodiado_revisor.md` | novo | |
| **`services/cautelares_get_info/scripts/main.py`** | **SOBRESCREVE** | nova CLI do serviço |
| `services/cautelares_get_info/scripts/pre_extracao.py` | novo | |
| `services/cautelares_get_info/scripts/consolidar.py` | novo | |
| `services/cautelares_get_info/scripts/__init__.py` | merge | |
| `services/cautelares_get_info/scripts/tests/*` | novo | dois testes |

## Sobre o `main.py` antigo

O `main.py` antigo do serviço `cautelares_get_info` será substituído pela
nova CLI, que cobre as quatro etapas do pipeline (reconciliar, pré-extrair,
consolidar, pipeline). Faça backup antes se quiser preservar lógica.

## Sobre `requirements.txt`

Adicione (ou faça merge) as três dependências na raiz do seu projeto:

```
rapidfuzz>=3.0.0
unidecode>=1.3.0
openpyxl>=3.1.0
```

## Após descompactar

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Rodar testes para validar
python -m services.cautelares_get_info.scripts.tests.test_extratores
python -m services.cautelares_get_info.scripts.tests.test_consolidador

# 3. Pipeline contra dados reais
python -m services.cautelares_get_info.scripts.main pipeline
```

## Pastas de dados

As pastas `files/`, `pdfs/`, `textos_extraidos/`, `pre_extraido/`, `result/`
estão no zip apenas com `.gitkeep` para documentar a estrutura — pode ignorá-las
se já existirem no seu projeto com conteúdo.
