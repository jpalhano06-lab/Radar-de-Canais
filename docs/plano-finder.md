# Plano: o que o Dotti Finder tem e falta na extensão do Radar

Pedido do usuário em 2026-11-05: "confira tudo que tem na extensão deles do youtube, precisamos de tudo".

Quem retoma: leia este arquivo inteiro, siga a primeira linha em aberto e atualize-o ao terminar cada item.

## De onde vem a lista

Dotti Finder 3.2.37, em `AppData\Local\DottiStudio\producoes\perfil_youtube\Default\Extensions\lpnjnahgabpibeaeocmflhdfhocpdkmi\3.2.37_0`:
79 arquivos, 60 deles de JS legível, sem comentários. A extensão do Radar é `extensao/`, 0.35.0 depois deste plano.

O catálogo oficial deles é o `funcoes.js` (34 funções). Li o manifesto, o catálogo, as rotas do servidor e as frases de
interface dos 60 arquivos de JS. Isso não é leitura linha a linha. Do que roda no servidor deles (a base de canais, o
índice de capas, os pesos da "chance para canal novo") só vejo o resultado, e `dottifinder.com` nunca foi aberto.

## Regras

- Só leitura em tudo que é da Dotti. Reimplementar o comportamento, nunca copiar código, CSS, fonte ou ícone.
- Uma função nova entra também em `radar/funcoes.py`: a tela Extensão e os planos leem de lá.
- Função sem código não entra no catálogo. `tags` e `som` estavam lá sem nunca terem existido.
- Sem `git push`. Commit local em `main` por lote pronto, com os testes passando.
- O Radar só se religa sem produção entrando pela fila. Mudança em `extensao/` só vale depois de recarregar a extensão.
- Relate o que foi visto funcionando e o que não foi. O Studio só se prova com a conta do usuário.

## Já existe no Radar

Nota de outlier, reação do público, inscritos, monetização, selo raro, dados do canal com gráficos, filtro da página com
receitas e planilha, esconder Shorts, provar capa e título, salvar canal, capa em tamanho real, painel lateral, canais
novos em alta, transcrição com salto no vídeo, números do seu canal, resumo da busca, copiar título, print do cartão,
Método Fantasma raiz, adaptado e premium, canais parecidos, análise do nicho, Vídeos do Nicho, "Hoje" no Studio, descrição
e tags com IA no Studio, automação do envio (monetização, questionário, mid-roll por intervalo), Alt+S, enviar para
produção.

## Falta

Estado: `[ ]` aberto, `[~]` em andamento, `[x]` pronto, `[-]` fora.

### Vídeo

- [x] 1. Tags do vídeo e do canal: aba Tags, chips e aviso dos 500 caracteres.
- [x] 2. Sons dos gestos: sintetizados, quietos com vídeo tocando. Sem prova de ouvido.
- [x] 3. Botões na barra do player: Capa, Transcrição e Print do quadro. Sem prova no player de verdade.
- [-] 4. Painel do vídeo abre sozinho: já era assim. Agora dá para desligar em Personalizar.
- [x] 5. Capas parecidas (`radar/capas.py`): dHash dos outliers, índice cresce sozinho depois de religar. Corte em 85: sorteadas chegam a 72. Mede composição, não assunto.
- [x] 6. Mesmo molde de título (`radar/molde.py`): 70% dos títulos reais têm molde. A coluna se preenche sozinha depois de religar.
- [x] 7. Por que este vídeo estourou: Claude real, resposta guardada.
- [x] 8. Títulos neste molde: Claude real.
- [x] 9. Levar o título para outra língua: Claude real, com aviso de faixa dublada. O aviso não foi visto num vídeo dublado de verdade.
- [x] 10. A receita da capa: visão real.
- [x] 11. RPM estimado do nicho no painel: faixa de `garimpo.NICHOS` menos os 45% do YouTube.
- [x] 12. Fila de modelagem pelo painel, perguntando o canal. Só no plano Pro, como a tela.
- [x] 13. Views por hora medida entre duas leituras com 1 h ou mais (`medir.velocidades`), com inscritos e `$` nos cartões.
- [x] 14. Seletor de língua na transcrição, com aviso quando a legenda não é a língua falada.

### Canal

- [x] 15. Crachá do canal (`radar/cracha.py`): juízes com peso e motivo, ritmo, projeção e queda. Cortes nossos, não medidos contra resultado. Conferido em 400 canais reais.
- [x] 16. Método Fantasma do canal: aba no canal, 10 vídeos por vez, línguas marcadas, títulos livres para copiar. Sem prova no YouTube real.
- [x] 17. O que o público pede (`radar/pedidos.py`): comentários pela API, filtro por palavras e por IA, sem o dono do canal. Provado com canal real: 9 pedidos de 10 vídeos.
- [x] 18. Salvar em pastas pela extensão: a caixa aparece depois de salvar.
- [x] 19. Aviso diário dos salvos que passaram de 5 vezes o normal.
- [x] 20. Medir o canal aberto pelo feed público: formato conferido no XML real.
- [x] 21. Parecidos: descer para os parecidos de um parecido, salvar na lista, procurar o estilo em outra língua. Vídeos do Nicho ganhou recortes, ordem e planilha.

### Busca

- [x] 22. Resumo da busca: concentração no maior canal e chance para canal novo. Pesos são um chute, e a tela diz isso.

### Studio

- [x] 23. Anúncios pela onda do som: pausas, distância mínima, tirar vermelhos e todos. Refeito em 2026-11-06 como o painel do Finder (`extensao/anuncios.js`): a cada, quantidade e pausas, prévia, trocar os atuais, tempo escrito em cada linha e conferido, zoom afastado sozinho. Testado numa tela simulada; o Studio de verdade ainda não.
- [x] 24. Visualizações engajadas: coluna no Conteúdo e linha no cartão do último vídeo. A coluna só foi vista em tela simulada, e a linha não foi vista.
- [x] 25. Foto do cartão com um clique, para colar com Ctrl+V. Botão visto em tela simulada; a cópia da imagem não foi provada.
- [x] 26. Onde o vídeo perde gente: as 3 maiores quedas e o que era falado. Só vista em tela simulada.
- [x] 27. Nota do título (`molde.nota`) e títulos no molde. A nota só mede o molde depois de religar o Radar. Os pesos são nossos.
- [x] 28. Capítulos da fala: Claude real numa legenda real. O botão só foi visto em tela simulada.
- [x] 29. Hora por país, lembrada por canal, e as horas com mais views. Só vista em tela simulada.
- [-] 30. Comprimir a capa para ficar abaixo de 2 MB: já existe em `publicar.js`.

### Claude e ChatGPT

- [x] 31. Botão no Claude e no ChatGPT (`chat-radar.js`): perguntas prontas e o comando do MCP. Nunca aberto nos sites de verdade.
- [x] 32. Ponte (`radar/ponte.py`): canal e busca pela aba aberta, transcrição e comentários pelo servidor, 4 ferramentas no MCP. Fila testada; sem prova com o Claude de verdade. Aba escondida responde devagar.

### Geral

- [x] 33. Personalizar no ícone da extensão: liga e desliga na hora.
- [x] 34. Patente por canais salvos, na janelinha. Nomes e degraus nossos.
- [x] 35. Números do seu canal fora do Studio: pedido de `leitor.js`, só as 48 horas. Sem prova com a conta real.
- [x] 36. Popup: contadores da aba, patente e atalhos.

## Fora, de propósito

- Planos, venda, funil e promoções: o Radar tem os planos dele.
- Pareamento por código e login pelo Google: a extensão entra por e-mail e senha no próprio Radar.
- Quem da equipe já salvou: o Radar tem 1 usuário, e não haveria nada para mostrar.
- Relatar um problema: lá o relato vai para a Dotti.
- Enviar ao robô do Dotti Studio: é a Nova produção.
