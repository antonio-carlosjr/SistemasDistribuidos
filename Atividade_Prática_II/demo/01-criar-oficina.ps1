. "$PSScriptRoot\_comum.ps1"

Titulo "Criacao de recurso -- 201 com Location e ETag"
Chamar -Metodo POST -Caminho "/oficinas" -Corpo "oficina"
Comentario "Location diz onde o recurso passou a existir; ETag identifica esta versao."
