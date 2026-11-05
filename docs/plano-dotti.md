# Plano: o que o Robô do Dotti tem e falta no Radar

Pedido do usuário em 2026-11-05, antes de dormir: "tudo do robo dotti que falta no radar, tudo que combinamos antes
que tinha no robo e não tinha no radar", "você tem permissão pra tudo, não pergunte nada", "quando acabar os créditos,
quando retornar, você voltar a trabalhar sem perguntar nada".

Quem retoma: leia este arquivo inteiro, siga a primeira linha em aberto, atualize-o ao terminar cada item.

## Regras do trabalho sem supervisão

- O produto "nosso" é o Radar (`Documents\Radar-de-Canais`, porta 8400) junto com a fábrica
  (`Documents\fabrica-videos`, porta 8080). Antes de dizer que algo falta, leia o módulo nos dois.
- Fonte do que o robô faz: `C:\Users\Palhano\AppData\Local\DottiStudio`. Só leitura. O núcleo é um `.pyd` compilado:
  o comportamento vem dos logs (`robo\robo.log`, `producoes\job_*\producao.log`). Não copie arquivos de lá para os
  nossos projetos (sons, transições, `lugares_nomes.json`), e não reuse cookies nem credenciais de lá.
- Nunca pare a fábrica com produção em andamento. Antes de parar: `criacao.json` em `processando`, gravação recente em
  `projetos\*`, `ffmpeg` rodando e `producoes_fila` em `produzindo`. Olhar só o `ffmpeg` não basta.
- Nunca rode `LIGAR-TIPLABS` (ele faz `git pull` e `stash`, e a fábrica tem dezenas de arquivos modificados). Para
  religar a fábrica: `uv run fabrica servidor --porta 8080 --frontend C:\Users\Palhano\Documents\tiplabs\front-editor`,
  escondida, com saída em `fabrica.log` e `fabrica.log.erros`.
- O Radar que roda é o checkout principal: mudança só vale depois de religar. Ele também só se religa sem produção
  entrando pela fila.
- Sem `git push`. Na fábrica, sem commit: os arquivos já têm mudanças de outro trabalho misturadas. No Radar, commit
  local em `main` por item pronto, com testes passando.
- Nada que saia da máquina em nome do usuário: sem publicar vídeo, sem mandar mensagem, sem compra, sem criar conta,
  sem digitar senha. Sem apagar projeto, vídeo ou dado do usuário.
- Relate o que foi medido e o que não foi. "Os testes passam" não prova o fluxo: rode o caminho de verdade.

## Itens

A lista é a da dissecção do Robô do Dotti: tudo o que ele tem e nós não, e o usuário mandou implementar tudo.

Estado: `[ ]` aberto, `[~]` em andamento, `[x]` pronto e testado, `[-]` já existia.

- [x] 1. Garimpo no YouTube: busca só em CC, trecho, cota, quadro real julgado, crop. Medido: 1 aceito (81), 3 reprovados (3, 50, 27); trecho montado num vídeo; SUBSCRIBE queimado reprovado. Sem produção inteira pela escolha do modelo
- [x] 2. Pool de contas: rotação, castigo, cópia dos cookies, `garimpo:` no perfil, aviso de conta única. Sem teste com conta real
- [x] 3. Robô em outras máquinas pelo Radar: `radar/maquinas.py`, `fabrica/robo.py` (`fabrica maquina`), `ROBO.ps1`, `INSTALAR-ROBO.ps1`. Provado por HTTP com fábrica simulada; nunca rodou em outro computador. Sobrepõe o `palhano/`, parado desde 12/10
- [x] 4. Repartir núcleos entre produções (`_parte_da_maquina`). Sem medida com dois renders juntos
- [x] 5. Escada de codificadores. AMF só se pedir: na montagem real perdeu da CPU (41 s contra 34 s, 3 de 3)
- [-] 6. Retomada por fase: `retomar_criacoes_interrompidas`, rota `/retomar`, `mcp_servidor.retomar_producoes`
- [-] 7. Custo: `custos_reais.resumo` dá total, por minuto e por cena; `radar/custos.py` dá a página por provedor
- [-] 8. Imagem por assinatura: limite, queda para a chave e 16 ao mesmo tempo (`imagens.processos`). Sem navegador, a RAM não limita
- [-] 9. Roteiro e miniatura: `radar/fila.py` escreve pelo Claude, `publicacao.py` faz as thumbs, `radar/trello.py` o cartão
- [x] 10. Volume -14 LUFS (`fabrica/render.py`). Medido no vídeo 17: -14,3 LUFS, pico -2,3 dBFS
- [x] 11. Estilos: 8 temas em `animacoes.TEMAS`, com escolha na Nova produção. Tema claro visto no navegador; sem vídeo inteiro
- [x] 12. Espinha: `item_citado` e `bloco.ancora` já existiam; trecho com título de outro item sai antes de baixar
- [~] 13. Acabamento: capítulos, CREDITS e entrega por atalho já existiam. Faxina pronta (`fabrica/faxina.py`), provada com render depois. Drive pela API NÃO feito: precisa do consentimento do usuário no Google; `entrega.pasta` apontada para o Drive para Desktop já resolve
- [x] 14. Garimpo pela tela do Radar: campo Footage real na Nova produção, provado no navegador até o Buscador

Fábrica religada em 2026-11-05 01:43 (PID 10688, `fabrica.log`). O render do vídeo 17 terminou bem, então a falha de
`Render (total)` não voltou; a causa não foi confirmada (o mais provável é `Faltam imagens`, `render.py:152`).
`so_clipes` corrigido em `fabrica/api.py` (o `render.py` tinha trocado por `adiantar_clipes`).

## Registro

- 2026-11-05: a tarefa agendada de retomada foi bloqueada pelo modo automático e não existe. Não contornar: retomar
  depende de alguém abrir a sessão.
- 2026-11-05: duas quedas do Windows (Kernel-Power 41) às 20:41 e 23:24. A das 23:24 zerou `custos_reais.json` do vídeo
  17, e 203 cenas geraram imagem 574 vezes. `registrar` agora não estoura e `gravar_atomico` faz fsync.
- 2026-11-05: garimpo só em Creative Commons por padrão, a regra escrita em `palhano/README.md`.
  `garimpo.so_creative_commons: false` abre para qualquer vídeo.
- 2026-11-05: `palhano/` (fora do git) é o painel de venda no modelo do robô, com máquinas e fila. Ninguém o liga desde
  12/10. Ler antes de construir qualquer coisa de robô.
- 2026-11-05, fim da noite. Em aberto: Drive pela API (consentimento do usuário), instalador .exe (hoje é
  `INSTALAR-ROBO.ps1`, nunca executado), robô em outro computador de verdade, dois renders juntos sem medida, produção
  inteira com garimpo pela escolha do modelo. Nada da fábrica foi commitado: rodar LIGAR-TIPLABS pode mandar para o stash.

