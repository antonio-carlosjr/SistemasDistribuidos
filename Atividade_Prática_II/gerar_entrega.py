"""Compoe o documento unico de entrega da AP2 em HTML e converte para PDF.

O documento e montado a partir dos arquivos que ja existem no repositorio --
modelagem, analise, roteiro de demonstracao e tabela de evidencias -- em vez de
duplicar o conteudo. Assim a entrega nunca diverge do que esta versionado: basta
regerar apos qualquer alteracao.

A conversao para PDF usa o Chrome ou o Edge em modo headless, que ja estao
instalados no Windows e produzem paginacao e tipografia melhores que as
bibliotecas puramente Python.

Uso:
    python gerar_entrega.py
"""

import base64
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import markdown

RAIZ = Path(__file__).resolve().parent
SAIDA = RAIZ / "entrega"
HTML = SAIDA / "AP2-entrega.html"
PDF = SAIDA / "AP2-entrega.pdf"

AUTOR = "Antonio Carlos Silva Junior"
DISCIPLINA = "Sistemas Distribuidos"
REPOSITORIO = "github.com/antonio-carlosjr/SistemasDistribuidos"

NAVEGADORES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]

EXTENSOES = ["tables", "fenced_code", "sane_lists", "attr_list"]


def para_html(caminho: Path, rebaixar: int = 0) -> str:
    """Converte um arquivo Markdown do repositorio em HTML.

    `rebaixar` empurra os niveis de titulo para baixo, para que o `#` de cada
    documento vire subsecao dentro da numeracao do documento de entrega.
    """
    texto = caminho.read_text(encoding="utf-8")

    # O primeiro titulo vira o titulo da secao, definido aqui e nao no arquivo.
    texto = re.sub(r"\A#\s+.*?\n", "", texto, count=1)

    if rebaixar:
        texto = re.sub(
            r"^(#{1,5}) ",
            lambda m: "#" * min(6, len(m.group(1)) + rebaixar) + " ",
            texto,
            flags=re.MULTILINE,
        )

    # Markdown padrao nao entende lista de tarefas; converte para simbolo,
    # senao o checklist sai como "[ ]" literal no documento.
    texto = re.sub(r'^(\s*[-*] )\[ \] ', lambda m: m.group(1) + "☐ ", texto, flags=re.MULTILINE)
    texto = re.sub(r'^(\s*[-*] )\[[xX]\] ', lambda m: m.group(1) + "☑ ", texto, flags=re.MULTILINE)

    corpo = markdown.markdown(texto, extensions=EXTENSOES)
    return embutir_imagens(corpo)


def embutir_imagens(corpo: str) -> str:
    """Troca referencias de imagem por data URI.

    Embutir mantem o PDF autocontido e evita que a conversao dependa de caminhos
    relativos resolvidos pelo navegador.
    """

    def trocar(match: re.Match) -> str:
        origem = match.group(1)
        arquivo = (RAIZ / "docs" / origem).resolve()
        if not arquivo.exists():
            print(f"  aviso: imagem nao encontrada -> {origem}", file=sys.stderr)
            return match.group(0)
        dados = base64.b64encode(arquivo.read_bytes()).decode("ascii")
        return f'src="data:image/png;base64,{dados}"'

    return re.sub(r'src="([^"]+\.png)"', trocar, corpo)


ESTILO = """
@page { size: A4; margin: 20mm 18mm 18mm 18mm; }
@page :first { margin: 0; }

* { box-sizing: border-box; }
/* Fundo e cor explicitos: sem eles, um visualizador em tema escuro pintaria
   o proprio fundo atras do documento. */
html { background: #ffffff; }
body {
  font-family: "Segoe UI", "Calibri", system-ui, sans-serif;
  font-size: 10.5pt; line-height: 1.55; color: #1a1a1a; margin: 0;
  background: #ffffff;
}

/* ------------------------------------------------------------------ capa */
.capa {
  height: 297mm; padding: 45mm 25mm 25mm 25mm; background: #ffffff;
  display: flex; flex-direction: column;
  border-top: 14mm solid #1f3a5f;
  page-break-after: always;
}
.capa .disciplina {
  font-size: 12pt; letter-spacing: .22em; text-transform: uppercase;
  color: #5a6b80; margin-bottom: 6mm;
}
.capa h1 {
  font-size: 30pt; line-height: 1.15; margin: 0 0 4mm 0;
  color: #1f3a5f; font-weight: 600; border: none;
}
.capa .subtitulo { font-size: 14pt; color: #445; margin-bottom: 14mm; }
.capa .regua { width: 40mm; height: 3px; background: #c8912f; margin-bottom: 14mm; }
.capa .resumo {
  font-size: 11pt; color: #333; max-width: 125mm; margin-bottom: auto;
}
.capa dl { margin: 0; font-size: 10.5pt; }
.capa dt {
  color: #5a6b80; text-transform: uppercase; letter-spacing: .1em;
  font-size: 8pt; margin-top: 5mm;
}
.capa dd { margin: 1mm 0 0 0; font-weight: 500; }

/* --------------------------------------------------------------- sumario */
.sumario { page-break-after: always; }
.sumario ol { list-style: none; counter-reset: s; padding: 0; }
.sumario li { counter-increment: s; padding: 2.2mm 0; border-bottom: 1px dotted #ccd; }
.sumario li::before {
  content: counter(s) "."; color: #c8912f; font-weight: 600;
  display: inline-block; width: 9mm;
}
.sumario .nota { color: #667; font-size: 9.5pt; margin-left: 9mm; }

/* --------------------------------------------------------------- titulos */
h1 {
  font-size: 19pt; color: #1f3a5f; margin: 0 0 6mm 0; padding-bottom: 2mm;
  border-bottom: 2px solid #c8912f; page-break-after: avoid;
}
h2 { font-size: 14pt; color: #1f3a5f; margin: 8mm 0 3mm; page-break-after: avoid; }
h3 { font-size: 11.5pt; color: #2c4a70; margin: 6mm 0 2mm; page-break-after: avoid; }
h4 { font-size: 10.5pt; color: #445; margin: 4mm 0 2mm; page-break-after: avoid; }
section { page-break-before: always; }

/* --------------------------------------------------------------- tabelas */
table {
  border-collapse: collapse; width: 100%; margin: 4mm 0;
  font-size: 9pt; page-break-inside: avoid;
}
th {
  background: #1f3a5f; color: #fff; text-align: left;
  padding: 2mm 2.5mm; font-weight: 600;
}
td { padding: 1.8mm 2.5mm; border-bottom: 1px solid #dde; vertical-align: top; }
tr:nth-child(even) td { background: #f6f8fa; }

/* --------------------------------------------------------------- codigo */
code {
  font-family: Consolas, "Cascadia Mono", monospace; font-size: 9pt;
  background: #eef1f5; padding: 0.4mm 1.2mm; border-radius: 2px; color: #234;
}
pre {
  background: #1e2430; color: #e6e9ef; padding: 3mm 4mm; border-radius: 3px;
  page-break-inside: avoid; font-size: 8.5pt; line-height: 1.4;
  /* Em papel nao existe rolagem horizontal: sem quebra, uma linha longa e
     silenciosamente cortada na borda da pagina. */
  white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere;
}
pre code { background: none; color: inherit; padding: 0; }

/* ------------------------------------------------------------- destaques */
blockquote {
  border-left: 3px solid #c8912f; background: #fdf8ee;
  margin: 4mm 0; padding: 2.5mm 4mm; color: #4a4335; page-break-inside: avoid;
}
img {
  max-width: 100%; border: 1px solid #ccd; border-radius: 3px;
  margin: 3mm 0; page-break-inside: avoid;
}
hr { border: none; border-top: 1px solid #dde; margin: 6mm 0; }
ul, ol { padding-left: 6mm; }
li { margin: 1mm 0; }
a { color: #1f3a5f; text-decoration: none; }
strong { color: #14243d; }
"""


def secao(numero: int, titulo: str, conteudo: str) -> str:
    return f'<section><h1>{numero}. {titulo}</h1>\n{conteudo}\n</section>'


def montar_html() -> str:
    hoje = date.today().strftime("%d/%m/%Y")

    secoes = [
        (1, "Visão geral e entregáveis",
            para_html(RAIZ / "docs" / "_resumo-entrega.md", 1)),
        (2, "Modelagem de recursos", para_html(RAIZ / "docs" / "modelagem.md", 1)),
        (3, "Execução e endpoints", para_html(RAIZ / "README.md", 1)),
        (4, "Tabela de evidências", para_html(RAIZ / "evidencias" / "tabela.md", 1)),
        (5, "Demonstração prática", para_html(RAIZ / "docs" / "demonstracao.md", 1)),
        (6, "Análise", para_html(RAIZ / "docs" / "analise.md", 1)),
    ]

    itens_sumario = "\n".join(
        f"<li>{titulo}</li>" for _, titulo, _ in secoes
    )

    corpo = "\n".join(secao(n, t, c) for n, t, c in secoes)

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>AP2 — API REST de Inscrições em Oficinas</title>
<style>{ESTILO}</style>
</head>
<body>

<div class="capa">
  <div class="disciplina">{DISCIPLINA}</div>
  <h1>API REST de Inscrições em Oficinas</h1>
  <div class="subtitulo">Atividade Prática II — Comunicação baseada em recursos</div>
  <div class="regua"></div>
  <div class="resumo">
    API REST para gestão de oficinas com vagas limitadas e das inscrições de
    participantes nelas. O domínio foi escolhido por possuir conflitos de
    concorrência intrínsecos — duas pessoas podem disputar a última vaga —,
    o que torna observáveis os problemas de idempotência, perda de atualização
    e distinção entre falha do servidor e ausência de resposta.
  </div>
  <dl>
    <dt>Aluno</dt><dd>{AUTOR}</dd>
    <dt>Repositório</dt><dd>{REPOSITORIO}</dd>
    <dt>Data</dt><dd>{hoje}</dd>
  </dl>
</div>

<div class="sumario">
  <h1>Sumário</h1>
  <ol>{itens_sumario}</ol>
  <p class="nota">
    Documento gerado por <code>gerar_entrega.py</code> a partir dos arquivos
    versionados no repositório. As capturas de tela e a tabela de evidências
    resultam de execuções reais, não de transcrição manual.
  </p>
</div>

{corpo}

</body>
</html>
"""


def encontrar_navegador() -> Path:
    for caminho in NAVEGADORES:
        if caminho.exists():
            return caminho
    achado = shutil.which("chrome") or shutil.which("msedge")
    if achado:
        return Path(achado)
    raise SystemExit("Chrome ou Edge nao encontrado para gerar o PDF.")


def main() -> int:
    SAIDA.mkdir(exist_ok=True)

    HTML.write_text(montar_html(), encoding="utf-8")
    print(f"HTML gerado: {HTML}  ({HTML.stat().st_size // 1024} KB)")

    navegador = encontrar_navegador()
    print(f"Convertendo com {navegador.name}...")

    subprocess.run(
        [
            str(navegador),
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={PDF}",
            HTML.as_uri(),
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )

    if not PDF.exists():
        raise SystemExit("O PDF nao foi produzido.")

    print(f"PDF gerado:  {PDF}  ({PDF.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
