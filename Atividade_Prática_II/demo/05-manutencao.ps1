. "$PSScriptRoot\_comum.ps1"

Titulo "Indisponibilidade -- 503 com Retry-After"
Chamar -Rotulo "ativando manutencao:" -Metodo POST -Caminho "/admin/manutencao" -Corpo "manutencao-on" -Admin -Linhas 1
Chamar -Rotulo "requisicao de dominio durante a manutencao:" -Caminho "/oficinas" -Linhas 9
& curl.exe -s -X POST "http://127.0.0.1:8000/admin/manutencao" -H "Content-Type: application/json" -H "X-Token-Admin: token-de-laboratorio" -d "@$PSScriptRoot\corpos\manutencao-off.json" | Out-Null
Comentario "Ha resposta: status e Retry-After. Sem servidor, nao haveria resposta alguma."
