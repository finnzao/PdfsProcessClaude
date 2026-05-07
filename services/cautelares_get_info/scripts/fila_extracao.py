"""
services/cautelares_get_info/scripts/fila_extracao.py — Gera fila de comandos
para o Claude Code extrair dados de custodiados dos markdowns.

Cada comando processa 2 processos (BATCH_SIZE). O próprio Claude Code salva
incrementalmente após cada processo, atualizando processos_claude_code.json.

O gerador da fila usa processos_claude_code.json como fonte da verdade
para saber quais processos já foram extraídos (ignora os já listados ali).

Uso:
    python -m services.cautelares_get_info.scripts.fila_extracao
    python -m services.cautelares_get_info.scripts.fila_extracao --src outra_pasta
    python -m services.cautelares_get_info.scripts.fila_extracao --filtro 8001
    python -m services.cautelares_get_info.scripts.fila_extracao --forcar
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

SERVICE_DIR = RAIZ / "services" / "cautelares_get_info"
TEXTOS_DIR = RAIZ / "textos_extraidos"
FILA_PATH = SERVICE_DIR / "fila_extracao.json"
CMDS_PATH = SERVICE_DIR / "comandos_extracao.txt"
CHECKPOINT_PATH = SERVICE_DIR / "checkpoint_extracao.json"
CONTROLE_PATH = SERVICE_DIR / "processos_claude_code.json"

BATCH_SIZE = 2


def carregar_controle_processos() -> dict:
    """Lê processos_claude_code.json — controle de retomada por processo."""
    if CONTROLE_PATH.exists():
        try:
            return json.loads(CONTROLE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  ⚠️  {CONTROLE_PATH.name} corrompido — começando do zero")
    return {
        "atualizado_em": datetime.now().isoformat(),
        "total_extraidos": 0,
        "processos": {},
    }


def numero_de_arquivo(nome_arquivo: str) -> str:
    """0001234_56_2024_8_05_0216.md -> 0001234-56.2024.8.05.0216"""
    stem = Path(nome_arquivo).stem
    partes = stem.split("_")
    if len(partes) >= 6:
        return f"{partes[0]}-{partes[1]}.{partes[2]}.{partes[3]}.{partes[4]}.{partes[5]}"
    return stem


def construir_comando(num_cmd: int, mds: list[Path]) -> str:
    """Monta o texto do comando a ser enviado ao Claude Code."""
    arquivos = "\n".join(
        f"  - textos_extraidos/{md.name}  ({numero_de_arquivo(md.name)})"
        for md in mds
    )
    numeros_cnj = " ".join(numero_de_arquivo(md.name) for md in mds)
    arquivos_cli = " ".join(f"textos_extraidos/{md.name}" for md in mds)

    return f"""# === CMD {num_cmd:03d} [EXTRACAO] [{len(mds)} processos] ===
# Processos: {numeros_cnj}
# Ao concluir: python run.py cautelares marcar-extracao {num_cmd} {numeros_cnj}

Leia o prompt em services/cautelares_get_info/prompts/prompt_extracao.md
e siga TODAS as regras dele. ATENÇÃO ESPECIAL à regra de salvamento
incremental: salve depois de CADA processo, não só no final.

Arquivos a processar (NESTA ORDEM):
{arquivos}

Use as ferramentas Read/Write para:

1. Ler services/cautelares_get_info/processos_claude_code.json (se existir)
   — pule processos cujo numero_processo já estiver listado lá.

2. Para cada arquivo .md (na ordem acima):
   a. Ler: {arquivos_cli}
   b. Extrair os dados do(s) réu(s) conforme schema do prompt
   c. APPEND no array em:
      services/cautelares_get_info/resultados/extracao/extracao_{num_cmd:03d}.json
      (se não existir, crie com [] e adicione; se existir, leia + adicione + salve)
   d. Atualizar services/cautelares_get_info/processos_claude_code.json
      adicionando entrada para o numero_processo recém-processado
   e. SÓ ENTÃO passar ao próximo arquivo

LEMBRETES CRÍTICOS:
- Salve INCREMENTALMENTE — se travar no meio, o que já foi feito permanece
- Pule processos já listados em processos_claude_code.json
- NUNCA confunda réu com vítima/testemunha
- Use `observacoes` para registrar gaps e dúvidas
- Status da cautelar exige verificação de imposição E cessação
- Em caso de dúvida, deixe campo vazio e explique em `observacoes`
"""


def gerar_fila(src_dir: Path, filtro: str = "*", forcar: bool = False) -> None:
    if not src_dir.exists():
        print(f"  Diretório não existe: {src_dir}")
        sys.exit(1)

    pad = f"{filtro}.md" if "*" in filtro else f"{filtro}*.md"
    mds = sorted(src_dir.glob(pad))
    if not mds:
        print(f"  Nenhum markdown encontrado em {src_dir} (filtro: {pad})")
        sys.exit(1)

    controle = carregar_controle_processos()
    ja_extraidos = set(controle.get("processos", {}).keys())
    total_encontrados = len(mds)

    if not forcar:
        mds = [md for md in mds if numero_de_arquivo(md.name) not in ja_extraidos]

    print(f"\n  Markdowns encontrados:    {total_encontrados}")
    print(f"  Já extraídos (controle):  {len(ja_extraidos)}")
    print(f"  Pendentes a processar:    {len(mds)}")

    if not mds:
        print("\n  Nada a fazer. Use --forcar para reprocessar tudo.")
        return

    # Monta comandos em batches de BATCH_SIZE
    comandos = []
    for i in range(0, len(mds), BATCH_SIZE):
        lote = mds[i:i + BATCH_SIZE]
        num_cmd = len(comandos) + 1
        comandos.append({
            "num": num_cmd,
            "processos": [numero_de_arquivo(md.name) for md in lote],
            "arquivos": [md.name for md in lote],
            "texto": construir_comando(num_cmd, lote),
        })

    # Salva fila.json
    fila = {
        "gerado_em": datetime.now().isoformat(),
        "service": "cautelares_get_info",
        "tipo": "extracao",
        "batch_size": BATCH_SIZE,
        "total_processos": len(mds),
        "total_comandos": len(comandos),
        "ja_extraidos_no_inicio": len(ja_extraidos),
        "comandos": [
            {"num": c["num"], "processos": c["processos"], "arquivos": c["arquivos"]}
            for c in comandos
        ],
    }
    FILA_PATH.write_text(
        json.dumps(fila, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Salva comandos.txt
    with open(CMDS_PATH, "w", encoding="utf-8") as f:
        f.write(f"# cautelares_get_info — extração de custodiados\n")
        f.write(f"# {len(comandos)} comandos | {len(mds)} processos | "
                f"batch={BATCH_SIZE} | gerado em {datetime.now():%d/%m/%Y %H:%M}\n")
        f.write(f"# Já extraídos antes desta fila: {len(ja_extraidos)}\n\n")
        for c in comandos:
            f.write(c["texto"] + "\n\n")

    print(f"\n  ✓ Fila gerada:")
    print(f"    {FILA_PATH}")
    print(f"    {CMDS_PATH}")
    print(f"\n  Total: {len(comandos)} comandos com até {BATCH_SIZE} processos cada")
    print(f"  Para executar: python auto_extrair_cautelares.py")


def main():
    p = argparse.ArgumentParser(description="Gera fila de extração de custodiados")
    p.add_argument("--src", default=str(TEXTOS_DIR), help="Pasta com markdowns")
    p.add_argument("--filtro", default="*", help="Filtro de arquivos (ex: 8001)")
    p.add_argument("--forcar", action="store_true",
                   help="Reprocessa mesmo os já listados em processos_claude_code.json")
    args = p.parse_args()

    gerar_fila(Path(args.src), args.filtro, args.forcar)


if __name__ == "__main__":
    main()
