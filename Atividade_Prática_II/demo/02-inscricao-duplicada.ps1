. "$PSScriptRoot\_comum.ps1"

Titulo "Unicidade -- o mesmo e-mail nao se inscreve duas vezes"
Chamar -Rotulo "primeira inscricao:" -Metodo POST -Caminho "/oficinas/1/inscricoes" -Corpo "bruno" -Linhas 1
Chamar -Rotulo "o mesmo e-mail, agora em maiusculas:" -Metodo POST -Caminho "/oficinas/1/inscricoes" -Corpo "bruno-maiusculo"
Comentario "409: repetir este POST conflita em vez de duplicar."
