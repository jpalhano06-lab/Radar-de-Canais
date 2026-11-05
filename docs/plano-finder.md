# Plano: o que o Dotti Finder tem e falta na extensão do Radar

Pedido do usuário em 2026-11-05: "confira tudo que tem na extensão deles do youtube, precisamos de tudo".

Quem retoma: leia este arquivo inteiro, siga a primeira linha em aberto e atualize-o ao terminar cada item.

## De onde vem a lista

Dotti Finder 3.2.37, em `AppData\Local\DottiStudio\producoes\perfil_youtube\Default\Extensions\lpnjnahgabpibeaeocmflhdfhocpdkmi\3.2.37_0`:
79 arquivos, 60 deles de JS legível, sem comentários. A extensão do Radar é `extensao/`, 0.31.1.

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
- [ ] 5. Capas parecidas que estouraram: índice de capas nos vídeos do banco, com a nota de parecença.
- [ ] 6. Mesmo molde de título: quem mais escreve assim, quantos canais, quanto rende.
- [ ] 7. Por que este vídeo estourou: IA decompõe o título, lê os primeiros segundos e explica o clique.
- [ ] 8. Títulos neste molde: 10 títulos para o assunto da pessoa, sem copiar.
- [ ] 9. Levar o título para outra língua, adaptado ao público de lá, avisando quando já há dublagem.
- [ ] 10. A receita da capa: IA olha a capa e escreve seis campos e a instrução pronta em inglês.
- [x] 11. RPM estimado do nicho no painel: faixa de `garimpo.NICHOS` menos os 45% do YouTube.
- [x] 12. Fila de modelagem pelo painel, perguntando o canal. Só no plano Pro, como a tela.
- [x] 13. Views por hora medida entre duas leituras com 1 h ou mais (`medir.velocidades`), com inscritos e `$` nos cartões.
- [x] 14. Seletor de língua na transcrição, com aviso quando a legenda não é a língua falada.

### Canal

- [ ] 15. Crachá do canal: tipo com o motivo, projeção de 30 dias, ritmo de postagem e queda dos vídeos novos.
- [ ] 16. Método Fantasma do canal: os 10 vídeos mais vistos e os 10 seguintes, por língua, com títulos para copiar.
- [ ] 17. O que o público pede: pedidos e perguntas dos comentários dos 10 vídeos mais vistos.
- [ ] 18. Salvar em pastas pela extensão. A coluna `salvos.pasta` já existe.
- [ ] 19. Aviso diário dos salvos que passaram de 5 vezes o normal.
- [ ] 20. Medir o canal aberto pelo feed público.
- [ ] 21. Parecidos: descer para os parecidos de um parecido e procurar o estilo em outra língua.

### Busca

- [ ] 22. Resumo da busca: chance para canal novo e concentração no maior canal.

### Studio

- [ ] 23. Anúncios pela onda do som: pausas, distância mínima, tirar os marcados de vermelho, tirar todos.
- [ ] 24. Visualizações engajadas: coluna no Conteúdo e linha nos cartões do Painel.
- [ ] 25. Foto do cartão com um clique, para colar com Ctrl+V.
- [ ] 26. Onde o vídeo perde gente: as 3 maiores quedas da retenção e o que era falado.
- [ ] 27. Nota do título e títulos no molde, embaixo do campo Título.
- [ ] 28. Capítulos da fala: lê a legenda e separa as partes do vídeo.
- [ ] 29. Hora por país do público, lembrada por canal, e as horas com mais views.
- [-] 30. Comprimir a capa para ficar abaixo de 2 MB: já existe em `publicar.js`.

### Claude e ChatGPT

- [ ] 31. Botão com perguntas prontas dentro do Claude e do ChatGPT, e ajuda para conectar o MCP do Radar.
- [ ] 32. A extensão lê o YouTube para o Claude e o ChatGPT: canal, vídeos, busca, transcrição e comentários.

### Geral

- [x] 33. Personalizar no ícone da extensão: liga e desliga na hora.
- [ ] 34. Patente e degraus por canais salvos.
- [ ] 35. Números do seu canal fora do Studio.
- [ ] 36. Popup: contadores da aba e atalhos.

## Fora, de propósito

- Planos, venda, funil e promoções: o Radar tem os planos dele.
- Pareamento por código e login pelo Google: a extensão entra por e-mail e senha no próprio Radar.
- Quem da equipe já salvou: o Radar tem 1 usuário, e não haveria nada para mostrar.
- Relatar um problema: lá o relato vai para a Dotti.
- Enviar ao robô do Dotti Studio: é a Nova produção.
