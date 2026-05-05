"""
services/cautelares_get_info/scripts/pre_extracao.py — Orquestra a pré-extração regex.

Este módulo recebe o markdown extraído de um processo e produz um JSON
com 70-85% dos campos preenchidos automaticamente, sem chamar LLM.

O Claude Code recebe esse JSON e age apenas como REVISOR, não extrator —
o que reduz drasticamente o tempo e o consumo de tokens.

Saída por processo:
    {
      "numero_processo": "...",
      "qualificacao": { ...DadosReu... },
      "cautelar": { ...DadosCautelar... },
      "metadados_processo": { classe, assunto, partes, etc. },
      "campos_para_revisao_llm": [ "lista de campos que precisam de julgamento" ],
      "estatisticas": { campos_preenchidos, confianca_media, ... }
    }

Uso:
    from services.cautelares_get_info.scripts.pre_extracao import processar_md

    resultado = processar_md("textos_extraidos/0001234_56_2024_8_05_0216.md")
    json.dump(resultado, open("pre_extraido/0001234.json", "w"))
"""

import json
import re
from pathlib import Path
from typing import Optional

from utils.extrator_qualificacao import extrair_qualificacao_reu, DadosReu
from utils.extrator_cautelar import extrair_cautelar, DadosCautelar


def _extrair_metadados_cabecalho(md: str) -> dict:
    """
    Lê o cabeçalho YAML-like do .md gerado pelo extrator.
    Formato esperado:
        # 0000000-00.0000.0.00.0000
        **Classe:** APOrd
        **Assunto:** Roubo
        ...
    """
    meta = {}
    # Linha 1: número do processo
    m_num = re.search(r"^#\s+(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})", md, re.M)
    if m_num:
        meta["numero_processo"] = m_num.group(1)

    campos = {
        "classe": r"\*\*Classe:\*\*\s*(.+?)(?:\s\s|\n)",
        "assunto": r"\*\*Assunto:\*\*\s*(.+?)(?:\s\s|\n)",
        "orgao_julgador": r"\*\*[ÓO]rg[ãa]o julgador:\*\*\s*(.+?)(?:\s\s|\n)",
        "valor_causa": r"\*\*Valor da causa:\*\*\s*(.+?)(?:\s\s|\n)",
        "distribuicao": r"\*\*Distribui[çc][aã]o:\*\*\s*(.+?)(?:\s\s|\n)",
        "polo_ativo": r"\*\*Autor/Exequente:\*\*\s*(.+?)(?:\s\s|\n)",
        "polo_passivo": r"\*\*R[ée]u/Executado:\*\*\s*(.+?)(?:\s\s|\n)",
        "total_paginas": r"\*\*Total de p[áa]ginas:\*\*\s*(\d+)",
        "total_pecas": r"\*\*Pe[çc]as identificadas:\*\*\s*(\d+)",
    }

    for chave, pat in campos.items():
        m = re.search(pat, md)
        if m:
            valor = m.group(1).strip()
            if chave in ("total_paginas", "total_pecas"):
                try:
                    valor = int(valor)
                except ValueError:
                    pass
            meta[chave] = valor

    return meta


def _decidir_campos_revisao(reu: DadosReu, cautelar: DadosCautelar) -> list[dict]:
    """
    Lista campos que o LLM precisa revisar/preencher, com motivo.
    Cada item é um foco específico de trabalho para o Claude Code.
    """
    revisao = []

    # ── Qualificação ──
    if not reu.nome:
        revisao.append({
            "campo": "nome",
            "motivo": "Nome do réu não localizado pela extração regex",
            "candidatos": reu.nomes_candidatos,
            "prioridade": "alta",
        })
    elif reu.confianca.get("nome") == "media" and reu.multiplos_reus:
        revisao.append({
            "campo": "nome",
            "motivo": "Múltiplos réus detectados — confirmar qual é o custodiado",
            "candidatos": reu.nomes_candidatos,
            "prioridade": "alta",
        })

    if not reu.cpf:
        revisao.append({
            "campo": "cpf",
            "motivo": "CPF do réu não localizado",
            "prioridade": "alta",
        })

    if not reu.rg and not reu.cpf:
        revisao.append({
            "campo": "rg_ou_cpf",
            "motivo": "Nenhum documento (CPF ou RG) localizado — obrigatório",
            "prioridade": "critica",
        })

    if not reu.endereco_bruto and not reu.logradouro:
        revisao.append({
            "campo": "endereco",
            "motivo": "Endereço não localizado — buscar em BO ou denúncia",
            "prioridade": "media",
        })

    # ── Cautelar ──
    if cautelar.status == "INDEFINIDO":
        revisao.append({
            "campo": "status_cautelar",
            "motivo": "Diagnóstico automático não conseguiu definir status",
            "prioridade": "critica",
        })
    elif cautelar.status == "SUSPEITA_ATIVA":
        revisao.append({
            "campo": "status_cautelar",
            "motivo": "Sursis/ANPP homologado sem prova de cumprimento — "
                      "verificar se período de prova encerrou",
            "prioridade": "critica",
        })
    elif cautelar.status == "ATIVA" and not cautelar.periodicidade:
        revisao.append({
            "campo": "periodicidade_cautelar",
            "motivo": "Cautelar ativa mas periodicidade não localizada na peça-fonte",
            "prioridade": "alta",
        })
    elif cautelar.confianca == "baixa":
        revisao.append({
            "campo": "cautelar_geral",
            "motivo": f"Confiança baixa: {cautelar.motivo_status}",
            "sinalizadores": cautelar.sinalizadores,
            "prioridade": "media",
        })

    return revisao


def _calcular_estatisticas(reu: DadosReu, cautelar: DadosCautelar) -> dict:
    """Métricas para a planilha de revisão humana."""
    campos_reu = reu.campos_preenchidos()
    total_campos_relevantes = 18  # nome, cpf, rg, mae, pai, nasc, etc.

    return {
        "campos_qualificacao_preenchidos": campos_reu,
        "total_campos_qualificacao": total_campos_relevantes,
        "completude_qualificacao_pct": round(campos_reu / total_campos_relevantes * 100, 1),
        "confianca_cautelar": cautelar.confianca,
        "status_cautelar": cautelar.status,
        "tem_documento": bool(reu.cpf or reu.rg),
        "tem_endereco": bool(reu.cep or reu.logradouro or reu.endereco_bruto),
        "tem_telefone": bool(reu.telefone),
    }


def processar_md(md_path: Path | str) -> dict:
    """
    Pipeline completo de pré-extração para um processo.
    Retorna dicionário pronto para serializar como JSON.
    """
    md_path = Path(md_path)
    md = md_path.read_text(encoding="utf-8")

    metadados = _extrair_metadados_cabecalho(md)
    reu = extrair_qualificacao_reu(md)
    cautelar = extrair_cautelar(md)
    revisao = _decidir_campos_revisao(reu, cautelar)
    stats = _calcular_estatisticas(reu, cautelar)

    return {
        "arquivo_md": md_path.name,
        "numero_processo": metadados.get("numero_processo", md_path.stem),
        "metadados_processo": metadados,
        "qualificacao": reu.to_dict(),
        "cautelar": cautelar.to_dict(),
        "campos_para_revisao_llm": revisao,
        "estatisticas": stats,
        "needs_llm": len(revisao) > 0 or cautelar.confianca != "alta",
    }


def processar_lote(
    diretorio_md: Path | str,
    diretorio_saida: Path | str,
    overwrite: bool = False,
) -> list[dict]:
    """Processa todos os .md do diretório e salva JSONs individuais."""
    diretorio_md = Path(diretorio_md)
    diretorio_saida = Path(diretorio_saida)
    diretorio_saida.mkdir(parents=True, exist_ok=True)

    resultados = []
    arquivos = sorted(diretorio_md.glob("*.md"))
    print(f"  Pré-extração de {len(arquivos)} processos...")

    for md in arquivos:
        json_out = diretorio_saida / (md.stem + ".json")
        if json_out.exists() and not overwrite:
            try:
                resultados.append(json.loads(json_out.read_text(encoding="utf-8")))
                continue
            except Exception:
                pass

        try:
            r = processar_md(md)
            json_out.write_text(
                json.dumps(r, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            resultados.append(r)
            stats = r["estatisticas"]
            status_cau = r["cautelar"]["status"]
            print(
                f"    {md.stem[:30]:<30} | "
                f"{stats['campos_qualificacao_preenchidos']:>2}/18 campos | "
                f"cautelar: {status_cau:<22} | "
                f"revisar: {len(r['campos_para_revisao_llm'])}"
            )
        except Exception as e:
            print(f"    {md.stem}: ERRO {e}")

    return resultados


if __name__ == "__main__":
    import sys
    diretorio_md = sys.argv[1] if len(sys.argv) > 1 else "textos_extraidos"
    diretorio_saida = sys.argv[2] if len(sys.argv) > 2 else "pre_extraido"
    processar_lote(diretorio_md, diretorio_saida)
