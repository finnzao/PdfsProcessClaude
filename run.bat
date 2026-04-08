@echo off
setlocal EnableDelayedExpansion

REM ================================================================
REM  ANALISE DE PROCESSOS CRIMINAIS - Sistema de Gestao
REM  Vara Criminal de Rio Real (0216) - TJBA  v1.0.0
REM ================================================================

set "SCRIPT_DIR=%~dp0"
if "!SCRIPT_DIR:~-1!"=="\" set "SCRIPT_DIR=!SCRIPT_DIR:~0,-1!"

set "DIR_PDFS=!SCRIPT_DIR!\pdfs"
set "DIR_TEXTOS=!SCRIPT_DIR!\textos_extraidos"
set "DIR_RESULTADOS=!SCRIPT_DIR!\resultados"
set "DIR_PROMPTS=!SCRIPT_DIR!\prompts"
set "DIR_SCRIPTS=!SCRIPT_DIR!\scripts"
set "DIR_LOGS=!SCRIPT_DIR!\logs"

set "CSV_FILE=!SCRIPT_DIR!\processos_crime_parados_mais_que_100_dias.csv"
set "CHECKPOINT=!SCRIPT_DIR!\checkpoint.json"
set "FILA=!SCRIPT_DIR!\fila_analise.json"
set "COMANDOS=!SCRIPT_DIR!\comandos_claude_code.txt"

if not exist "!DIR_PDFS!" mkdir "!DIR_PDFS!"
if not exist "!DIR_TEXTOS!" mkdir "!DIR_TEXTOS!"
if not exist "!DIR_RESULTADOS!" mkdir "!DIR_RESULTADOS!"
if not exist "!DIR_PROMPTS!" mkdir "!DIR_PROMPTS!"
if not exist "!DIR_SCRIPTS!" mkdir "!DIR_SCRIPTS!"
if not exist "!DIR_LOGS!" mkdir "!DIR_LOGS!"

REM Encontrar Python
set "PY="
python --version >nul 2>&1 && set "PY=python"
if not defined PY python3 --version >nul 2>&1 && set "PY=python3"

REM Roteamento
set "CMD=%~1"
if "!CMD!"=="" goto :menu
if /i "!CMD!"=="setup" goto :do_setup
if /i "!CMD!"=="extrair" goto :do_extrair
if /i "!CMD!"=="fila" goto :do_fila
if /i "!CMD!"=="analisar" goto :do_analisar
if /i "!CMD!"=="pausa" goto :do_pausa
if /i "!CMD!"=="status" goto :do_status
if /i "!CMD!"=="consolidar" goto :do_consolidar
if /i "!CMD!"=="reset" goto :do_reset
if /i "!CMD!"=="auto" goto :do_auto
if /i "!CMD!"=="help" goto :do_help
if /i "!CMD!"=="--help" goto :do_help
if /i "!CMD!"=="-h" goto :do_help
echo.
echo   [ERRO] Comando desconhecido: !CMD!
echo   Use: run.bat help
echo.
pause
goto :fim


REM ================================================================
REM SETUP
REM ================================================================
:do_setup
cls
echo.
echo   =========================================================
echo    ANALISE DE PROCESSOS CRIMINAIS - SETUP
echo   =========================================================
echo.
set "ERROS=0"

echo   [1/4] Dependencias do sistema
echo   --------------------------------------------------------

if defined PY (
    echo   [OK] Python: !PY!
) else (
    echo   [XX] Python NAO encontrado
    echo        Instale: https://www.python.org/downloads/
    echo        Marque "Add Python to PATH" durante a instalacao!
    set /a ERROS+=1
)

set "HAS_TESS=0"
tesseract --version >nul 2>&1 && set "HAS_TESS=1"
if "!HAS_TESS!"=="1" (
    echo   [OK] Tesseract OCR
) else (
    echo   [!!] Tesseract OCR nao encontrado (so precisa se tiver paginas escaneadas)
    echo        Instale: https://github.com/UB-Mannheim/tesseract/wiki
)

set "HAS_NODE=0"
node --version >nul 2>&1 && set "HAS_NODE=1"
if "!HAS_NODE!"=="1" (
    echo   [OK] Node.js
) else (
    echo   [!!] Node.js nao encontrado (necessario para Claude Code)
    echo        Instale: https://nodejs.org/
)

set "HAS_CLAUDE=0"
claude --version >nul 2>&1 && set "HAS_CLAUDE=1"
if "!HAS_CLAUDE!"=="1" (
    echo   [OK] Claude Code
) else (
    echo   [XX] Claude Code NAO encontrado
    echo        Instale: npm install -g @anthropic-ai/claude-code
    set /a ERROS+=1
)

echo.
echo   [2/4] Modulos Python
echo   --------------------------------------------------------

if defined PY (
    !PY! -c "import pdfplumber" >nul 2>&1
    if !errorlevel! equ 0 (echo   [OK] pdfplumber) else (
        echo   [XX] pdfplumber nao instalado. Rode: pip install pdfplumber
        set /a ERROS+=1
    )
    !PY! -c "import pypdf" >nul 2>&1
    if !errorlevel! equ 0 (echo   [OK] pypdf) else (
        echo   [XX] pypdf nao instalado. Rode: pip install pypdf
        set /a ERROS+=1
    )
) else (
    echo   [XX] Python nao disponivel para verificar modulos.
)

echo.
echo   [3/4] Estrutura do projeto
echo   --------------------------------------------------------

if exist "!CSV_FILE!" (
    echo   [OK] CSV encontrado
) else (
    echo   [XX] CSV nao encontrado
    set /a ERROS+=1
)

set "PC=0"
for %%f in ("!DIR_PROMPTS!\*.md") do set /a PC+=1
if !PC! gtr 0 (echo   [OK] Prompts: !PC! arquivos) else (
    echo   [XX] Nenhum prompt encontrado
    set /a ERROS+=1
)

set "SC=0"
for %%s in (extrair_processos.py analisar_processos.py marcar_concluido.py sessao.py consolidar.py) do (
    if exist "!DIR_SCRIPTS!\%%s" (
        set /a SC+=1
    ) else (
        echo   [XX] Faltando: scripts\%%s
        set /a ERROS+=1
    )
)
if !SC! equ 5 echo   [OK] Todos os 5 scripts presentes

echo.
echo   [4/4] PDFs
echo   --------------------------------------------------------

set "PDF_COUNT=0"
for %%f in ("!DIR_PDFS!\*.pdf") do set /a PDF_COUNT+=1
if !PDF_COUNT! gtr 0 (
    echo   [OK] !PDF_COUNT! PDFs em pdfs\
) else (
    echo   [!!] Nenhum PDF em pdfs\
    echo        Coloque os PDFs dos processos na pasta pdfs\
)

echo.
echo   ========================================================
if !ERROS! equ 0 (
    echo   RESULTADO: Tudo OK!
    if !PDF_COUNT! gtr 0 (
        echo   Proximo passo: run.bat extrair
    ) else (
        echo   Proximo passo: colocar PDFs em pdfs\ e depois run.bat extrair
    )
) else (
    echo   RESULTADO: !ERROS! problema(s) encontrado(s). Corrija e rode novamente.
)
echo   ========================================================
echo.
pause
goto :fim


REM ================================================================
REM EXTRAIR
REM ================================================================
:do_extrair
cls
echo.
echo   =========================================================
echo    EXTRACAO DE TEXTO DOS PDFs
echo   =========================================================
echo.

if not defined PY (
    echo   [XX] Python nao encontrado. Rode run.bat setup primeiro.
    echo.
    pause
    goto :fim
)

set "PDF_COUNT=0"
for %%f in ("!DIR_PDFS!\*.pdf") do set /a PDF_COUNT+=1
if !PDF_COUNT! equ 0 (
    echo   [XX] Nenhum PDF encontrado em pdfs\
    echo       Coloque os PDFs dos processos na pasta pdfs\
    echo.
    pause
    goto :fim
)

set "TXT_COUNT=0"
for %%f in ("!DIR_TEXTOS!\*.txt") do set /a TXT_COUNT+=1
if !TXT_COUNT! gtr 0 (
    echo   [!!] Ja existem !TXT_COUNT! textos extraidos.
    echo.
    set /p "RESP=  Reprocessar todos? [s/N]: "
    if /i not "!RESP!"=="s" (
        echo.
        echo   Mantendo existentes. Proximo passo: run.bat fila
        echo.
        pause
        goto :fim
    )
)

echo   Iniciando extracao de !PDF_COUNT! PDFs...
echo   Isso pode demorar. Aguarde.
echo.

cd /d "!SCRIPT_DIR!"
!PY! scripts\extrair_processos.py

echo.
set "TXT_COUNT=0"
for %%f in ("!DIR_TEXTOS!\*.txt") do set /a TXT_COUNT+=1
echo   Textos gerados: !TXT_COUNT!
echo   Proximo passo: run.bat fila
echo.
pause
goto :fim


REM ================================================================
REM FILA
REM ================================================================
:do_fila
cls
echo.
echo   =========================================================
echo    GERACAO DE FILA DE COMANDOS
echo   =========================================================
echo.

if not defined PY (
    echo   [XX] Python nao encontrado.
    pause
    goto :fim
)

if not exist "!CSV_FILE!" (
    echo   [XX] CSV nao encontrado.
    pause
    goto :fim
)

set "TXT_COUNT=0"
for %%f in ("!DIR_TEXTOS!\*.txt") do set /a TXT_COUNT+=1
if !TXT_COUNT! equ 0 (
    echo   [!!] Nenhum texto extraido. Analise sera limitada (so dados do CSV).
    echo.
    set /p "RESP=  Continuar? [s/N]: "
    if /i not "!RESP!"=="s" (
        echo   Rode run.bat extrair primeiro.
        pause
        goto :fim
    )
) else (
    echo   [OK] !TXT_COUNT! textos extraidos disponiveis
)

echo.
echo   Gerando fila de comandos...
echo.

cd /d "!SCRIPT_DIR!"
!PY! scripts\analisar_processos.py

echo.
if exist "!COMANDOS!" (
    echo   [OK] Arquivo comandos_claude_code.txt gerado!
    echo   Proximo passo: run.bat analisar
) else (
    echo   [XX] Falha ao gerar fila.
)
echo.
pause
goto :fim


REM ================================================================
REM ANALISAR
REM ================================================================
:do_analisar
cls
echo.
echo   =========================================================
echo    SESSAO DE ANALISE - CLAUDE CODE
echo   =========================================================
echo.

if not defined PY (
    echo   [XX] Python nao encontrado.
    pause
    goto :fim
)

if not exist "!COMANDOS!" (
    echo   [XX] Arquivo de comandos nao encontrado.
    echo       Rode run.bat fila primeiro.
    echo.
    pause
    goto :fim
)

set "HAS_CLAUDE=0"
claude --version >nul 2>&1 && set "HAS_CLAUDE=1"
if "!HAS_CLAUDE!"=="0" (
    echo   [XX] Claude Code nao encontrado.
    echo       Instale: npm install -g @anthropic-ai/claude-code
    echo.
    pause
    goto :fim
)

REM Ler estado do checkpoint
set "ULTIMO_CMD=0"
set "ANALISADOS=0"
set "TOTAL_CMD=0"
set "TOTAL_PROC=0"

if exist "!CHECKPOINT!" (
    for /f "delims=" %%v in ('!PY! -c "import json;print(json.load(open(r'!CHECKPOINT!')).get('ultimo_comando',0))" 2^>nul') do set "ULTIMO_CMD=%%v"
    for /f "delims=" %%v in ('!PY! -c "import json;print(len(json.load(open(r'!CHECKPOINT!')).get('processos_analisados',{})))" 2^>nul') do set "ANALISADOS=%%v"
)
if exist "!FILA!" (
    for /f "delims=" %%v in ('!PY! -c "import json;print(json.load(open(r'!FILA!')).get('total_comandos',0))" 2^>nul') do set "TOTAL_CMD=%%v"
    for /f "delims=" %%v in ('!PY! -c "import json;print(json.load(open(r'!FILA!')).get('total_processos',0))" 2^>nul') do set "TOTAL_PROC=%%v"
)

set /a "PROXIMO=ULTIMO_CMD + 1"
set /a "RESTANTES=TOTAL_CMD - ULTIMO_CMD"

if !RESTANTES! leq 0 (
    echo   Todos os comandos ja foram executados!
    echo   Proximo passo: run.bat consolidar
    echo.
    pause
    goto :fim
)

set /a "TEMPO_MIN=RESTANTES * 5"
set /a "TEMPO_MAX=RESTANTES * 8"

echo   ESTADO ATUAL
echo   --------------------------------------------------------
echo   Processos:  !ANALISADOS! / !TOTAL_PROC! analisados
echo   Comandos:   !ULTIMO_CMD! / !TOTAL_CMD! concluidos
echo   Restam:     !RESTANTES! comandos (~!TEMPO_MIN!-!TEMPO_MAX! min)
echo   Proximo:    COMANDO #!PROXIMO!
echo   --------------------------------------------------------

REM Registrar sessao
cd /d "!SCRIPT_DIR!"
!PY! scripts\sessao.py inicio

echo.
echo   =========================================================
echo    INSTRUCOES
echo   =========================================================
echo.
echo   1. O Claude Code vai abrir agora.
echo.
echo   2. Abra comandos_claude_code.txt em outro editor
echo      (Notepad, VS Code, etc.)
echo.
echo   3. Copie o COMANDO #!PROXIMO! e cole no Claude Code.
echo.
echo   4. Quando terminar, cole a linha "Ao concluir:" que
echo      aparece no topo de cada comando.
echo.
echo   5. Repita para cada comando seguinte.
echo.
echo   QUANDO O LIMITE EXPIRAR:
echo   Saia do Claude Code (Ctrl+C) e rode: run.bat pausa
echo   =========================================================
echo.

set /p "RESP=  Abrir Claude Code agora? [S/n]: "
if /i "!RESP!"=="n" (
    echo.
    echo   Para abrir manualmente: cd projeto_final
    echo   Depois: claude
    echo   Ao terminar: run.bat pausa
    echo.
    pause
    goto :fim
)

echo.
echo   Abrindo Claude Code...
echo   (Ao sair, a janela vai perguntar se quer registrar pausa)
echo.

cd /d "!SCRIPT_DIR!"
call claude

echo.
echo   Claude Code encerrado.
echo.
set /p "RESP=  Registrar pausa da sessao? [S/n]: "
if /i not "!RESP!"=="n" (
    cd /d "!SCRIPT_DIR!"
    !PY! scripts\sessao.py fim
)
echo.
echo   Para retomar: run.bat analisar
echo.
pause
goto :fim


REM ================================================================
REM PAUSA
REM ================================================================
:do_pausa
cls
echo.
echo   =========================================================
echo    REGISTRAR PAUSA
echo   =========================================================
echo.

if not defined PY (
    echo   [XX] Python nao encontrado.
    pause
    goto :fim
)

if not exist "!CHECKPOINT!" (
    echo   Nenhuma sessao ativa para pausar.
    echo.
    pause
    goto :fim
)

cd /d "!SCRIPT_DIR!"
!PY! scripts\sessao.py fim

echo.
echo   Para retomar depois: run.bat analisar
echo.
pause
goto :fim


REM ================================================================
REM STATUS
REM ================================================================
:do_status
cls
echo.
echo   =========================================================
echo    STATUS DA ANALISE
echo   =========================================================
echo.

if not exist "!FILA!" (
    if not exist "!CHECKPOINT!" (
        echo   Nenhuma analise em andamento.
        echo.
        echo   Pipeline:
        echo     1. run.bat setup       verificar dependencias
        echo     2. run.bat extrair     extrair texto dos PDFs
        echo     3. run.bat fila        gerar comandos
        echo     4. run.bat analisar    abrir Claude Code
        echo     5. run.bat consolidar  relatorio final
        echo.
        pause
        goto :fim
    )
)

set "PDF_COUNT=0"
set "TXT_COUNT=0"
set "RES_COUNT=0"
for %%f in ("!DIR_PDFS!\*.pdf") do set /a PDF_COUNT+=1
for %%f in ("!DIR_TEXTOS!\*.txt") do set /a TXT_COUNT+=1
for %%f in ("!DIR_RESULTADOS!\analise_*.csv") do set /a RES_COUNT+=1

echo   PIPELINE
echo   --------------------------------------------------------
if !PDF_COUNT! gtr 0 (echo   [OK] PDFs:        !PDF_COUNT! arquivos) else (echo   [--] PDFs:        nenhum)
if !TXT_COUNT! gtr 0 (echo   [OK] Extracao:    !TXT_COUNT! textos) else (echo   [--] Extracao:    nao executada)
if exist "!COMANDOS!" (echo   [OK] Fila:        gerada) else (echo   [--] Fila:        nao gerada)
if !RES_COUNT! gtr 0 (echo   [OK] Resultados:  !RES_COUNT! arquivos) else (echo   [--] Resultados:  nenhum)
if exist "!SCRIPT_DIR!\relatorio_final.csv" (echo   [OK] Relatorio:   gerado) else (echo   [--] Relatorio:   nao gerado)
echo.

if defined PY (
    if exist "!FILA!" (
        cd /d "!SCRIPT_DIR!"
        !PY! scripts\analisar_processos.py --status
    )
)
pause
goto :fim


REM ================================================================
REM CONSOLIDAR
REM ================================================================
:do_consolidar
cls
echo.
echo   =========================================================
echo    CONSOLIDACAO DOS RESULTADOS
echo   =========================================================
echo.

if not defined PY (
    echo   [XX] Python nao encontrado.
    pause
    goto :fim
)

set "RES_COUNT=0"
for %%f in ("!DIR_RESULTADOS!\analise_*.csv") do set /a RES_COUNT+=1
if !RES_COUNT! equ 0 (
    echo   [XX] Nenhum resultado em resultados\
    echo       Execute run.bat analisar primeiro.
    echo.
    pause
    goto :fim
)

echo   Consolidando !RES_COUNT! arquivos de resultado...
echo.

cd /d "!SCRIPT_DIR!"
!PY! scripts\consolidar.py

echo.
if exist "!SCRIPT_DIR!\relatorio_final.csv" (
    echo   [OK] relatorio_final.csv gerado!
    echo   [OK] resumo_estatisticas.txt
)
echo.
pause
goto :fim


REM ================================================================
REM RESET
REM ================================================================
:do_reset
cls
echo.
echo   =========================================================
echo    RESET - RECOMECAR ANALISE
echo   =========================================================
echo.
echo   ATENCAO: Isso apaga todo o progresso da analise.
echo.
echo   Sera removido:
echo     - checkpoint.json
echo     - fila_analise.json
echo     - comandos_claude_code.txt
echo     - mapeamento_processos.json
echo     - Arquivos em resultados\
echo     - relatorio_final.csv
echo     - resumo_estatisticas.txt
echo.
echo   NAO sera removido:
echo     - PDFs em pdfs\
echo     - Textos em textos_extraidos\
echo     - Prompts e scripts
echo.

set /p "RESP=  Tem certeza? [s/N]: "
if /i not "!RESP!"=="s" (
    echo   Cancelado.
    echo.
    pause
    goto :fim
)

if exist "!CHECKPOINT!" del /q "!CHECKPOINT!"
if exist "!FILA!" del /q "!FILA!"
if exist "!COMANDOS!" del /q "!COMANDOS!"
if exist "!SCRIPT_DIR!\mapeamento_processos.json" del /q "!SCRIPT_DIR!\mapeamento_processos.json"
if exist "!SCRIPT_DIR!\relatorio_final.csv" del /q "!SCRIPT_DIR!\relatorio_final.csv"
if exist "!SCRIPT_DIR!\resumo_estatisticas.txt" del /q "!SCRIPT_DIR!\resumo_estatisticas.txt"
if exist "!SCRIPT_DIR!\relatorio_extracao.json" del /q "!SCRIPT_DIR!\relatorio_extracao.json"
if exist "!DIR_RESULTADOS!\analise_*.csv" del /q "!DIR_RESULTADOS!\analise_*.csv"

echo.
echo   [OK] Reset concluido.
echo   Textos extraidos foram mantidos.
echo   Proximo passo: run.bat fila
echo.
pause
goto :fim


REM ================================================================
REM AUTO
REM ================================================================
:do_auto
cls
echo.
echo   =========================================================
echo    MODO AUTOMATICO
echo   =========================================================
echo.

if not defined PY (
    echo   [XX] Python nao encontrado. Rode run.bat setup.
    pause
    goto :fim
)

if not exist "!CSV_FILE!" (
    echo   [XX] CSV nao encontrado. Rode run.bat setup.
    pause
    goto :fim
)

echo   [1/3] Verificando ambiente... OK
echo.

REM Extrair
set "PDF_COUNT=0"
set "TXT_COUNT=0"
for %%f in ("!DIR_PDFS!\*.pdf") do set /a PDF_COUNT+=1
for %%f in ("!DIR_TEXTOS!\*.txt") do set /a TXT_COUNT+=1

echo   [2/3] Extracao de PDFs...
if !PDF_COUNT! gtr 0 (
    if !TXT_COUNT! lss !PDF_COUNT! (
        echo         Extraindo !PDF_COUNT! PDFs...
        echo.
        cd /d "!SCRIPT_DIR!"
        !PY! scripts\extrair_processos.py
        echo.
    ) else (
        echo         Ja extraidos: !TXT_COUNT! textos. Pulando.
    )
) else (
    if !TXT_COUNT! gtr 0 (
        echo         Ja extraidos: !TXT_COUNT! textos. Pulando.
    ) else (
        echo         [!!] Nenhum PDF para extrair.
    )
)

echo.
echo   [3/3] Gerando fila de comandos...
echo.
cd /d "!SCRIPT_DIR!"
!PY! scripts\analisar_processos.py

echo.
echo   =========================================================
echo   Pipeline preparado!
echo   Proximo passo: run.bat analisar
echo   =========================================================
echo.
pause
goto :fim


REM ================================================================
REM HELP
REM ================================================================
:do_help
cls
echo.
echo   =========================================================
echo    ANALISE DE PROCESSOS CRIMINAIS - AJUDA
echo   =========================================================
echo.
echo   Pipeline principal:
echo     run.bat setup         Verificar dependencias e ambiente
echo     run.bat extrair       Extrair texto dos PDFs (OCR + limpeza)
echo     run.bat fila          Gerar fila de comandos para Claude Code
echo     run.bat analisar      Iniciar sessao no Claude Code
echo     run.bat consolidar    Juntar resultados em relatorio final
echo.
echo   Controle de sessao:
echo     run.bat pausa         Registrar pausa (sessao expirou)
echo     run.bat status        Ver progresso detalhado
echo.
echo   Utilitarios:
echo     run.bat auto          Executar pipeline completo ate Claude Code
echo     run.bat reset         Recomecar analise do zero
echo     run.bat help          Mostrar esta ajuda
echo.
echo   Fluxo tipico:
echo     run.bat setup
echo     run.bat extrair
echo     run.bat fila
echo     run.bat analisar
echo       (pausa se limite expirar)
echo     run.bat analisar   (retoma de onde parou)
echo     run.bat consolidar
echo.
echo   Atalho:
echo     run.bat auto   (faz setup+extrair+fila de uma vez)
echo.
pause
goto :fim


REM ================================================================
REM MENU
REM ================================================================
:menu
cls
echo.
echo   =========================================================
echo    ANALISE DE PROCESSOS CRIMINAIS
echo    Vara Criminal de Rio Real (0216) - TJBA
echo   =========================================================
echo.

set "PDF_COUNT=0"
set "TXT_COUNT=0"
set "RES_COUNT=0"
for %%f in ("!DIR_PDFS!\*.pdf") do set /a PDF_COUNT+=1
for %%f in ("!DIR_TEXTOS!\*.txt") do set /a TXT_COUNT+=1
for %%f in ("!DIR_RESULTADOS!\analise_*.csv") do set /a RES_COUNT+=1

echo   PDFs: !PDF_COUNT!   Textos: !TXT_COUNT!   Resultados: !RES_COUNT!

if exist "!CHECKPOINT!" (
    if defined PY (
        for /f "delims=" %%v in ('!PY! -c "import json;print(len(json.load(open(r'!CHECKPOINT!')).get('processos_analisados',{})))" 2^>nul') do set "ANA=%%v"
        for /f "delims=" %%v in ('!PY! -c "import json;print(json.load(open(r'!CHECKPOINT!')).get('ultimo_comando',0))" 2^>nul') do set "ULT=%%v"
        set "TOT=?"
        if exist "!FILA!" (
            for /f "delims=" %%v in ('!PY! -c "import json;print(json.load(open(r'!FILA!')).get('total_comandos',0))" 2^>nul') do set "TOT=%%v"
        )
        echo   Analisados: !ANA!   Comandos: !ULT!/!TOT!
    )
)
echo   --------------------------------------------------------
echo.

REM Detectar recomendacao
set "REC=1"
if exist "!SCRIPT_DIR!\relatorio_final.csv" (set "REC=0"
) else if !RES_COUNT! gtr 0 (set "REC=5"
) else if exist "!COMANDOS!" (set "REC=4"
) else if !TXT_COUNT! gtr 0 (set "REC=3"
) else if !PDF_COUNT! gtr 0 (set "REC=2"
)

echo   O que deseja fazer?
echo.
if "!REC!"=="1" (echo     1. Verificar dependencias     * recomendado) else (echo     1. Verificar dependencias)
if "!REC!"=="2" (echo     2. Extrair texto dos PDFs     * recomendado) else (echo     2. Extrair texto dos PDFs)
if "!REC!"=="3" (echo     3. Gerar fila de comandos     * recomendado) else (echo     3. Gerar fila de comandos)
if "!REC!"=="4" (echo     4. Abrir Claude Code          * recomendado) else (echo     4. Abrir Claude Code)
if "!REC!"=="5" (echo     5. Gerar relatorio final      * recomendado) else (echo     5. Gerar relatorio final)
echo     6. Ver progresso
echo     7. Registrar pausa
echo     8. Recomecar do zero
echo     9. Sair
echo.

set /p "CHOICE=  Escolha [1-9]: "

if "!CHOICE!"=="1" goto :do_setup
if "!CHOICE!"=="2" goto :do_extrair
if "!CHOICE!"=="3" goto :do_fila
if "!CHOICE!"=="4" goto :do_analisar
if "!CHOICE!"=="5" goto :do_consolidar
if "!CHOICE!"=="6" goto :do_status
if "!CHOICE!"=="7" goto :do_pausa
if "!CHOICE!"=="8" goto :do_reset
if "!CHOICE!"=="9" goto :fim
echo.
echo   Opcao invalida.
pause
goto :menu

:fim
endlocal
