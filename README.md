# Codex Context Observer

Painel local de contexto e estimativas de custo por conversa para o Codex desktop.

Plugin independente, sem afiliação com a OpenAI. Interface em português. Versão **0.4.0**.

## Instalação pelo GitHub

Requisitos: Codex desktop com suporte a plugins/MCP Apps, Codex CLI com `plugin marketplace` e **Python 3.10+** disponível como `python3` no PATH do aplicativo. Testado em macOS com Codex CLI 0.163.0; outros sistemas não foram validados.

```sh
codex plugin marketplace add leonardo-devcode/codex-context-observer
codex plugin add context-observer@codex-context-observer
```

Você também pode escolher **Context Observer** na lista de marketplaces da interface e instalar **Contexto da conversa**. Reinicie o Codex e, na conversa desejada, peça:

> Abra o painel de contexto desta conversa.

Na primeira abertura, o plugin cria um ambiente Python isolado e instala `tiktoken` e suas dependências pelo pip. Essa etapa precisa de internet e pode levar até alguns minutos. As próximas aberturas reutilizam o ambiente. O vocabulário do tokenizer e o HTML compilado estão incluídos; Node.js não é necessário para usar o plugin.

O painel fica fixo na conversa em que foi aberto. Atualiza os dados a cada dois segundos enquanto visível. Para outra conversa, abra um painel nela.

### Atualizar

```sh
codex plugin marketplace upgrade codex-context-observer
codex plugin add context-observer@codex-context-observer
```

Reinicie o Codex e reabra o painel. Confira a versão no cabeçalho. Para remover, use o gerenciamento de plugins do Codex. O cache Python não é removido automaticamente.

Quem instalou a edição local anterior (`context-observer@leonardo-context-local`) deve desativá-la na interface antes de ativar esta edição, evitando duas ferramentas com o mesmo nome. A instalação pelo GitHub não altera nem remove a edição anterior.

## O que aparece no painel

- Uso estimado da janela de contexto, entrada/saída da última chamada e histórico.
- Composição parcial do texto registrado, em tokens e porcentagem da janela.
- Inventário de skills e namespaces MCP presentes na sessão, com detalhes e busca.
- Histórico de compactações e medições anteriores/posteriores.
- Estimativas em USD por modelo quando há evidência de cobrança por API OpenAI.
- Versão, identidade da conversa e estado de atualização.

Não faz chamadas ao modelo ou à API de faturamento. Não acompanha automaticamente a conversa selecionada na interface.

## Detecção de cobrança

O plugin prioriza a autenticação registrada na resposta/turno ou evidência de plano ChatGPT associada ao turno. Quando o histórico não informa a cobrança, pode usar `codex login status` como referência local, consultado no máximo uma vez por minuto. A saída bruta e as credenciais nunca são retornadas ao painel.

**Login atual por API não comprova a cobrança passada nem a conta utilizada pelo aplicativo desktop.** Nesse caso o painel sinaliza a origem da estimativa. Uso identificado como ChatGPT é excluído da estimativa de API. Evidências conflitantes ficam sem preço. Se há respostas explicitamente identificadas como API, o subtotal usa somente essas respostas.

Usamos tokens por resposta (`token_usage_record`), deduplicados pelo ID. O modelo vem da resposta ou do seu turno. Modalidades registradas têm prioridade; **Standard é a referência assumida** quando a modalidade falta. Cache e raciocínio não são contados duas vezes. Contexto longo é tratado por chamada.

A tabela `pricing.json` foi consultada em **17/10/2026** e não se atualiza automaticamente. Ela é aplicada ao histórico sem reconstruir tarifas antigas. Modelos e provedores sem tarifa ficam sem preço. A estimativa não é uma fatura: não inclui impostos, descontos, ferramentas pagas à parte, acréscimos regionais ou subagentes em outros arquivos.

## Privacidade e limites

A coleta lê o índice SQLite e o arquivo JSONL da conversa dentro de `CODEX_HOME` (por padrão, `~/.codex`). O formato é interno e pode mudar. Conversas sem registro local compatível não são suportadas.

O processamento é local. A interface recebe métricas, nome/ID da conversa, caminhos de origem e inventários de recursos, que podem conter nomes e referências privadas. Não recebe o texto bruto das mensagens/instruções nem chaves. Não há telemetria ou envio para um servidor do projeto. Evite publicar capturas ou relatórios com informações privadas. A instalação inicial acessa o registro de pacotes Python para baixar dependências.

A composição usa `o200k_base`, uma aproximação não confirmada como tokenizer exato do modelo. Categorias podem se sobrepor; **não devem ser somadas**. Conteúdo criptografado e multimodal é excluído. Após compactação, as estimativas usam o histórico legível preservado e os novos registros. Ferramentas sem catálogo acessível ficam indisponíveis.

## Solução de problemas

- **O MCP não inicia:** confirme que `python3 --version` funciona no ambiente do Codex. Em Linux pode ser necessário instalar o pacote `python3-venv` da distribuição. Confira os logs de inicialização e a conexão com o registro Python na primeira abertura.
- **Categorias indisponíveis:** verifique se o tokenizer foi instalado e se a sessão contém os registros correspondentes. Não há valores substitutos inventados.
- **Custo indisponível:** a sessão pode estar em ChatGPT, sem contadores detalhados ou sem tarifas correspondentes. Na conta de API, confirme a autenticação do CLI com `codex login status`.
- **Conversa não encontrada:** o painel só suporta sessões locais ativas no índice `state_5.sqlite`. Arquivos arquivados, sessões remotas e mudanças de formato podem impedir a coleta.
- **Vínculo expirado:** feche o painel e abra outro na mesma conversa.

O ambiente Python fica em `~/Library/Caches/codex-context-observer` no macOS ou `${XDG_CACHE_HOME:-~/.cache}/codex-context-observer` nos demais sistemas. `CONTEXT_OBSERVER_DATA_DIR` permite escolher outro diretório de cache. Não há alteração no Python global.

## Desenvolvimento

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r plugins/context-observer/requirements.txt
npm ci --prefix plugins/context-observer
npm run build --prefix plugins/context-observer
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
node tests/test_billing_ui.mjs
node tests/test_fixed_bridge.mjs
node tests/test_ui_state.mjs
```

O arquivo `panel.html` é versionado para permitir instalação sem Node. Após alterar a interface, reconstrua-o. Os testes usam dados sintéticos; não exigem chaves de API ou conversas reais.

## Licença e fontes

MIT para o código original; avisos de terceiros em [THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt).

- [Plugins e marketplaces no Codex](https://developers.openai.com/plugins/build/plugins)
- [Autenticação do Codex](https://developers.openai.com/codex/auth)
- [Preços da API OpenAI](https://developers.openai.com/api/docs/pricing)
- [Contagem de custo por chamada](https://developers.openai.com/cookbook/articles/per_run_spending_controller_responses_api)
