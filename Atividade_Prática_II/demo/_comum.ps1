# Funcoes compartilhadas pelos passos da demonstracao.
#
# Cada passo imprime o comando em forma legivel antes de executa-lo, para que a
# tela mostre o que esta sendo pedido e nao apenas o resultado.

$BASE = "http://127.0.0.1:8000"
$CORPOS = Join-Path $PSScriptRoot "corpos"

function Titulo($texto) {
    Write-Host ""
    Write-Host "  $texto" -ForegroundColor Cyan
    Write-Host ""
}

function Comentario($texto) {
    Write-Host "  $texto" -ForegroundColor DarkGray
}

# Executa uma chamada curl mostrando antes uma versao legivel do comando.
#   -Rotulo   texto exibido acima da resposta
#   -Metodo   verbo HTTP
#   -Caminho  caminho do recurso, sem o host
#   -Corpo    nome do arquivo em demo/corpos, sem extensao
#   -IfMatch  valor do cabecalho If-Match
#   -Linhas   quantas linhas da resposta exibir (0 = todas)
function Chamar {
    param(
        [string]$Rotulo,
        [string]$Metodo = "GET",
        [string]$Caminho,
        [string]$Corpo,
        [string]$IfMatch,
        [switch]$Admin,
        [int]$Linhas = 0
    )

    $mostrado = "curl -i -X $Metodo $BASE$Caminho"
    if ($Corpo)  { $mostrado += " -d @demo/corpos/$Corpo.json" }
    if ($IfMatch) { $mostrado += " -H 'If-Match: `"$IfMatch`"'" }
    if ($Admin)  { $mostrado += " -H 'X-Token-Admin: ...'" }

    if ($Rotulo) { Comentario $Rotulo }
    Write-Host "  $mostrado" -ForegroundColor White

    $argumentos = @("-i", "-s", "-X", $Metodo, "$BASE$Caminho")
    if ($Corpo) {
        $argumentos += @("-H", "Content-Type: application/json",
                         "-d", "@$CORPOS\$Corpo.json")
    }
    if ($IfMatch) { $argumentos += @("-H", "If-Match: `"$IfMatch`"") }
    if ($Admin)   { $argumentos += @("-H", "X-Token-Admin: token-de-laboratorio") }

    $saida = & curl.exe @argumentos
    if ($Linhas -gt 0) { $saida = $saida | Select-Object -First $Linhas }
    $saida | ForEach-Object {
        if ($_ -match "^HTTP/") { Write-Host "  $_" -ForegroundColor Yellow }
        else { Write-Host "  $_" }
    }
    Write-Host ""
}
