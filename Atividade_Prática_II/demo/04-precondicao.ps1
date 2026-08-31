. "$PSScriptRoot\_comum.ps1"

Titulo "Concorrencia -- escrita exige a precondicao If-Match"
Chamar -Rotulo "sem If-Match:" -Metodo PATCH -Caminho "/oficinas/1" -Corpo "titulo" -Linhas 1
Chamar -Rotulo "com um ETag obsoleto:" -Metodo PATCH -Caminho "/oficinas/1" -Corpo "titulo" -IfMatch "99" -Linhas 1
Chamar -Rotulo "com o ETag vigente:" -Metodo PATCH -Caminho "/oficinas/1" -Corpo "titulo" -IfMatch "1" -Linhas 8
Comentario "428 exige a precondicao, 412 detecta escrita concorrente, 200 avanca o ETag."
