. "$PSScriptRoot\_comum.ps1"

Titulo "Capacidade -- a oficina 3 ja esta lotada"
Chamar -Metodo POST -Caminho "/oficinas/3/inscricoes" -Corpo "carla"
Comentario "409, e nao 422: a representacao esta correta, o estado e que nao permite."
