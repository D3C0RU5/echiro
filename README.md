# echiro

Monorepo com API em Python/FastAPI e aplicação web em React/TypeScript/Vite.

## Dev Container

Abra esta pasta no VS Code com a extensão **Dev Containers** e execute **Dev Containers: Reopen in Container**. A criação do container instala Node.js 24 LTS, Python 3.12, `uv` e as dependências dos dois projetos.

Depois, execute `npm run dev:api` e `npm run dev:web` em dois terminais do container. As portas 8000 e 5173 são encaminhadas automaticamente.

## Pré-requisitos

- Python 3.12 ou superior
- [uv](https://docs.astral.sh/uv/)
- Node.js 20.19+ ou 22.12+ e npm

## Instalação

```bash
npm install
cd apps/api && uv sync && cd ../..
```

## Desenvolvimento

Em dois terminais, na raiz do projeto:

```bash
npm run dev:api
```

```bash
npm run dev:web
```

- Aplicação web: http://localhost:5173
- API: http://localhost:8000/api/health
- Documentação interativa da API: http://localhost:8000/docs

O Vite encaminha as chamadas `/api` para o FastAPI durante o desenvolvimento.

## Build do frontend

```bash
npm run build
```

O resultado fica em `apps/web/dist`.

## Cadastro e configuração de projetos (fases 2 e 3)

Inicie a API e o frontend com os comandos de desenvolvimento acima e abra
http://localhost:5173. Na tela de projetos:

1. Cadastre nome, URL do Jira Cloud, chave do projeto, e-mail Atlassian e token de API.
2. Use **Testar conexão salva** para conferir o acesso de leitura.
3. Clique em **Buscar opções do Jira**, escolha um quadro Scrum e clique em **Carregar quadro**.
4. Selecione tipos de tarefa, subtarefa e bug; colunas de trabalho; status finais próprios para trabalho e bugs; e uma ou mais sprints.
5. Informe a data de adoção de IA, quando conhecida, e salve a configuração.

Use **Novo projeto** para cadastrar a segunda conexão. Os projetos têm credenciais,
metadados e configurações independentes. O ZUR foi cadastrado neste ambiente com as
regras aprovadas e as 20 sprints disponíveis; a data de adoção de IA ficou em branco.
O segundo projeto real permanece adiado. O suporte a duas conexões foi verificado
com dados simulados, sem criar um projeto fictício no banco de uso.

Na edição, e-mail e token vazios preservam os valores salvos; preenchê-los substitui
as credenciais. Eles nunca são recuperados pelo frontend. Nome e regras são editáveis.
URL e chave identificam a origem dos dados e permanecem fixas após o cadastro;
para outra origem, cadastre outro projeto.

As consultas de metadados são manuais e somente de leitura. Reabrir a aplicação
recupera o cache local, sem consultar o Jira. Salvar a configuração não dispara
coleta de tickets. A sincronização é solicitada no dashboard; o cálculo usa somente
a base local e é atualizado ao abrir a análise ou solicitar recálculo.
As opções são obtidas do Jira, sem nomes fixos de colunas ou status. Tipos de tarefa,
subtarefa e bug devem ser distintos; colunas de trabalho não podem conter status
finais de tarefas. Histórias e épicos devem permanecer fora dos tipos selecionados.

### Banco, credenciais e versões

O SQLite fica em `apps/api/.local/echiro.sqlite3` e usa migrações incrementais
controladas por `PRAGMA user_version`, aplicadas em transação na inicialização.
A primeira migração modela projetos, conexões, versões de configuração, cache de
metadados, sprints, tickets, eventos, execuções de sincronização e resultados.
IDs externos são associados ao ID local do projeto, com chaves compostas e
restrições de integridade para impedir mistura ou duplicação entre conexões.

E-mail e token são criptografados com Fernet, da biblioteca `cryptography`.
A chave é gerada automaticamente em `~/.config/echiro/credentials.key`, fora do
banco e do repositório. Banco e chave usam permissão `600`; a pasta nova da chave
usa `700`. Essa proteção depende também da conta do sistema: quem controla essa
conta e a chave consegue abrir as credenciais.

Para alterar os caminhos, exporte `ECHIRO_DATABASE_PATH` e `ECHIRO_KEY_PATH` antes
de iniciar a API. A chave precisa ficar fora do repositório e da pasta do banco.
Cadastre as credenciais do Jira pela interface; a execução normal não precisa de
arquivo `.env`. O banco e a chave não devem ser versionados.

Para backup, pare a API e copie o banco e a chave para destinos protegidos e
separados. Para restaurar, configure os caminhos e mantenha a chave com permissão
`600`. Perder a chave impede abrir as credenciais existentes; a API não gera uma
nova chave silenciosamente quando já há conexões. Não remova a chave ao reiniciar.

Cada mudança efetiva das regras ou da data de IA cria uma versão imutável da
configuração. Os resultados registram a versão usada: a API distingue
`not_calculated`, `current` e `recalculation_required`, e a interface sinaliza
resultados de uma versão anterior. Salvar a mesma configuração não cria outra versão.
O dashboard recalcula a base local quando a configuração ou a sincronização muda.
O botão **Recalcular indicadores** também permite refazer o cálculo sem acessar o Jira.

### API e execução local

Os servidores escutam em `127.0.0.1`, nas portas 8000 e 5173. O encaminhamento do
Dev Container deve permanecer restrito a `localhost`, sem compartilhar portas.
A API valida o cliente local, o Host e a origem das requisições do navegador;
não habilita CORS para sites externos. A aplicação não tem tela de login.

- `GET /api/projects`: lista projetos sem credenciais.
- `POST /api/projects`: cadastra conexão.
- `GET /api/projects/{id}` e `PUT /api/projects/{id}`: consulta e edita cadastro.
- `POST /api/projects/{id}/test-connection`: testa as credenciais salvas.
- `GET /api/projects/{id}/metadata`: lê somente o cache local.
- `POST /api/projects/{id}/metadata`: busca opções, com `board_id` opcional no JSON.
- `PUT /api/projects/{id}/configuration`: valida e salva regras versionadas.

Os formatos completos estão em http://localhost:8000/docs. Respostas de validação
não incluem os valores recebidos, para evitar devolver tokens em erros.

A organização da API separa `integrations` (Jira), `persistence` (banco e proteção),
`domain` (validações), `projects` (cadastro), `synchronization` (fase 4) e `metrics`
(fase 5). As ferramentas de prova continuam disponíveis sem depender do banco.

Para verificar a API, o domínio e o isolamento com duas conexões simuladas:

```bash
cd apps/api
uv run python -m unittest discover -s tests -v
```

Os testes usam banco e chave temporários, não leem tokens reais e não acessam o Jira.

## Sincronização e dashboard (fases 4 a 6)

Abra um projeto na barra lateral e entre em **Dashboard**. Clique em
**Sincronizar agora** para buscar os tickets visíveis de todo o projeto, incluindo
bugs fora do quadro e das sprints selecionadas. A primeira execução pode levar
alguns minutos; o progresso mostra históricos lidos e reaproveitados.

A coleta usa somente GET no Jira, percorre todas as páginas e limita as leituras
simultâneas a três tickets por projeto. Erros transitórios de rede, HTTP 429 e 5xx
permitem até três tentativas por requisição, com espera progressiva e respeito ao
`Retry-After` informado pelo Jira. Erros de credencial e permissão não são repetidos.
Somente uma coleta por projeto pode ficar em execução; projetos distintos são isolados.
Execute a API em um único processo, como no comando de desenvolvimento, sem workers extras.

As sincronizações seguintes percorrem novamente a lista de tickets e comparam
`updated`; apenas tickets novos ou alterados exigem reler o changelog completo.
Isso permite atualizações incrementais sem depender de um cursor antigo de busca.
A lista não é filtrada por tipo ou sprint. Ao reler um ticket, a API confere que
seus campos não mudaram durante a leitura do histórico.

Dados são preparados separadamente da base publicada. Uma falha mantém os últimos
resultados e mostra a tentativa incompleta. Use **Retomar coleta** após resolver a
falha: a busca é refeita e históricos já preparados são reaproveitados quando
`updated` continua igual. Depois de reiniciar a API, execuções em andamento ficam
interrompidas; nada reinicia sozinho. Se as regras mudarem, use uma nova coleta.
A publicação bem-sucedida atualiza tickets, sprints, eventos e o corte temporal na
mesma transação. Chaves compostas impedem duplicação. Eventos já armazenados não
são removidos porque uma consulta posterior deixou de retorná-los; a divergência
passa a ser uma limitação explícita que exige conferência.

No dashboard:

- Use **Incluir selecionadas** para marcar as sprints que quer analisar ou
  **Excluir selecionadas** para marcar as que devem ficar de fora. A troca de modo
  preserva o conjunto exibido; **Marcar todas** e **Desmarcar todas** atuam sobre as
  marcações do modo ativo. Totais, gráficos e comparação seguem o mesmo filtro.
- Clique em um número para listar e filtrar as chaves dos tickets, abrir o Jira e
  conferir eventos de primeira conclusão ou reabertura.
- Alterne o gráfico entre volumes e bugs divididos por tarefas/subtarefas trabalhadas.
- Registre a data de adoção de IA na configuração para comparar antes e depois.
- Consulte a última sincronização, a versão usada no cálculo e as limitações da base.

As tarefas e subtarefas valem uma unidade cada, sem eliminar filhas quando a mãe
é contada. Trabalho iniciado antes continua elegível até a conclusão, durante sua
participação na sprint. Remoções preservam o trabalho anterior; pendências não são
transferidas automaticamente. Primeiras conclusões são identificadas no histórico
global do ticket; reabrir e concluir novamente não cria outra primeira conclusão.
Reaberturas mostram tickets distintos por sprint; quando há vários eventos para
um mesmo ticket, a tabela também informa a quantidade de eventos.

Bugs são contados quando estiveram abertos em qualquer parte do intervalo, sem
exigir participação na sprint. Novos mais existentes equivalem ao total. Denominador
zero aparece como **Não calculável**. Histórico insuficiente aparece como
**Indisponível**, com as evidências verificáveis separadas do total não certificado.
O zero só é exibido quando a base disponível sustenta a ausência de tickets elegíveis.

Intervalos seguem `[início, fim)`: `startDate`, encerramento real `completeDate`
nas fechadas e corte fixo da coleta nas ativas. Datas ausentes não usam o fim
planejado como substituto. Sprints futuras ficam sem indicadores. Datas são
comparadas em UTC e exibidas em America/Sao_Paulo. Sprints sobrepostas preservam
suas próprias janelas; as somas por sprint podem repetir um ticket presente em
mais de uma delas e não representam um total global de tickets distintos.

A data de IA representa meia-noite em São Paulo. Sprints que atravessam o marco
são de transição. A comparação usa somente sprints encerradas e com todos os
indicadores disponíveis da seleção atual; transição, ativas e incompletas ficam
fora das médias e têm suas quantidades visíveis. A proporção do grupo usa a soma
de bugs dividida pela soma de trabalhadas, sem calcular a média das proporções.
Não há comparação de produtividade entre projetos nem afirmação de causalidade.

### Limitações verificadas no ZUR

O fluxo real foi executado no ZUR: 1.000 tickets, 20 sprints, repetição da
sincronização com 1.000 históricos reaproveitados e nenhuma duplicação de eventos.
Foram conferidos os exemplos anteriores de trabalho carregado, primeiras
conclusões, bugs reabertos e 1.069 intervalos de participação de subtarefas.

A reconstrução diferencia períodos de tarefa padrão e de subtarefa, usando os
vínculos e as conversões de tipo históricos. Seis tickets não têm evidência própria
de sprint no período anterior à conversão em subtarefa. O valor atual herdado não
é projetado para esse passado: os intervalos desconhecidos permanecem indisponíveis.
Uma lacuna só bloqueia o indicador quando pode alterar sua contagem: trabalho
potencial durante o período desconhecido, primeira conclusão ou reabertura nesse
período. Ausência de atividade elegível permite determinar o resultado mesmo sem
conhecer a associação à sprint. O bloqueio excessivo que afetava oito sprints foi
corrigido no motor versão 2. Trabalho, entregas e bugs estão disponíveis nas 19
sprints já iniciadas; a futura continua sem indicadores. Lacunas realmente relevantes
permanecem identificadas nas listas de limitações.

Permissões podem ocultar tickets e eventos. A busca não descobre tickets já
movidos para fora do projeto antes da primeira coleta. Perda posterior de
visibilidade, eventos anteriormente presentes que deixem de ser retornados,
mudanças do quadro e datas/hierarquias ausentes são sinalizadas. A configuração
histórica de colunas não foi reconstruída; os IDs configurados são aplicados ao
histórico conforme a decisão aprovada. Não há snapshot transacional do Jira.

O segundo projeto real segue adiado. Dois projetos independentes foram verificados
com Jira simulado, inclusive pelo navegador, mas a fase 7 e a liberação completa da
primeira versão permanecem pendentes da validação real dessa segunda conexão.

Evidências locais, fora do Git e com permissão `600`:
`apps/api/.local/first-version-validation.json` (conferência agregada) e
`apps/api/.local/first-version-dashboard.json` (resultados e tickets privados).

Endpoints adicionais:

- `GET /api/projects/{id}/sync`: progresso, execuções recentes e última publicação.
- `POST /api/projects/{id}/sync`: solicita sincronização manual.
- `POST /api/projects/{id}/sync/resume`: retoma a tentativa incompleta.
- `GET /api/projects/{id}/dashboard`: recupera/calcula indicadores usando apenas o banco local.
- `POST /api/projects/{id}/recalculate`: refaz o cálculo sobre a base publicada.

## Prova de integração com Jira Cloud (fase 1)

Estas ferramentas são auxiliares da validação inicial. Para o uso cotidiano,
cadastre as conexões pela interface e sincronize pelo dashboard.

Para executar a prova manual, a partir da raiz:

```bash
cd apps/api
uv run python -m app.jira_probe --project 1
```

O comando solicita interativamente URL do site Jira Cloud, chave do projeto,
ID do quadro, e-mail Atlassian e token de API. O token é digitado de forma oculta
e não é salvo pelo comando. Sem opções, somente o projeto 1 é consultado;
use `--project 2` para a segunda conexão ou `--all-projects` para ambas.

Também é possível fornecer variáveis de ambiente `JIRA_PROBE_1_URL`,
`JIRA_PROBE_1_PROJECT_KEY`, `JIRA_PROBE_1_BOARD_ID`, `JIRA_PROBE_1_EMAIL` e
`JIRA_PROBE_1_TOKEN`, com o prefixo `JIRA_PROBE_2_` para a segunda conexão.
Use uma conta com acesso de leitura. Não envie tokens pelo chat nem os coloque
em arquivos versionados. O repositório não fornece mais `.env` ou `.env.example`.

A prova usa somente requisições GET, confirma autenticação, consulta o projeto,
verifica sua presença no quadro, lê configuração de colunas/status, tipos e sprints,
e, por padrão, busca uma amostra dos cinco tickets mais antigos com seu changelog paginado.
Não calcula indicadores nem faz sincronização. Redirecionamentos HTTP são recusados para proteger as credenciais.

O relatório é salvo em `apps/api/.local/jira-probe.json` ao executar na pasta da API,
com acesso restrito ao proprietário e fora do controle de versão. Contém IDs,
metadados, datas, contagens e valores anteriores/novos das mudanças de status e
sprint; não inclui credenciais, autores, descrições, comentários nem mudanças de
outros campos. Para outro destino, use `--output CAMINHO` e mantenha o
arquivo fora do controle de versão. O código de saída é `1` se alguma conexão falhar.

Para conferir os dados e o histórico do ZUR (segundo item da fase 1), gere um
relatório separado sem substituir a primeira prova:

```bash
uv run python -m app.jira_probe --project 1 --sample-size 5 --output .local/jira-probe-step-2.json
```

O tamanho da amostra aceita de 1 a 100 tickets. Para conferir tickets específicos,
repita `--issue`; essa seleção substitui a busca dos tickets mais antigos:

```bash
uv run python -m app.jira_probe --project 1 --issue ZUR-5 --issue ZUR-33 --output .local/jira-probe-selected.json
```

O relatório inclui nomes e IDs de tipos/status por tipo, correspondência atual
entre colunas e status, sprints com estado e datas originais, tipo e tarefa mãe
dos tickets, valores atuais de sprint e mudanças de status/sprint com data e
valores anteriores/novos. O campo de sprint é identificado pelo schema do Jira,
sem depender do nome traduzido ou de um ID fixo. Campos ausentes são indicados
como indisponíveis e não são herdados da tarefa mãe. Datas ausentes são `null`;
as regras efetivas de intervalo estão documentadas no plano e são aplicadas pelo motor de métricas.

No modo padrão, todas as páginas de changelog de cada ticket selecionado são
solicitadas, mas a busca de tickets é limitada à amostra. `status: read_access_verified` confirma a
leitura dos endpoints; não significa que todos os casos ou todo o histórico foram
validados. Os tipos e status exportados ainda não constituem regras de contagem.

Para percorrer todos os tickets visíveis do projeto (terceiro item da fase 1):

```bash
uv run python -m app.jira_probe --project 1 --all-issues --page-size 20 --output .local/jira-probe-step-3.json
```

`--all-issues` percorre a busca por `nextPageToken`, sem restringir tipo, quadro ou
vínculo à sprint, e consulta todas as páginas do changelog de cada ticket. Isso
inclui os bugs visíveis do projeto, mesmo fora do quadro. A execução é sequencial
e manual, exibe progresso e pode demorar. `--page-size` aceita de 1 a 100; valores
menores ajudam a exercitar várias páginas. A API pode retornar menos itens que o
solicitado. `--all-issues` não pode ser combinado com `--issue`.

Nesse modo, os históricos ficam em `connections[].issues` e a seção `collection`
informa o escopo, a conclusão da busca, tickets descobertos, históricos lidos,
chaves ainda não lidas e falhas. `pagination` registra quantidade de páginas,
itens e conclusão por consulta; cursores não são exportados. Se não informar
`--output`, o relatório completo usa `.local/jira-probe-full.json`, separado da
amostra padrão.

Uma falha durante a busca ou um changelog interrompe a coleta e gera
`status: incomplete`, código de saída `1` e relatório com as evidências já lidas.
Não há tentativas automáticas nem retomada nesta prova; execute novamente após
resolver a falha. Páginas repetidas, cursor sem avanço, totais alterados e sinais
de término contraditórios também impedem apresentar a coleta como completa.
Falhas na autenticação ou nos metadados iniciais são registradas como `failed`.

`collection.complete: true` significa que a busca e os changelogs retornados pela
API foram percorridos até o término. Não comprova acesso a tickets ocultos,
excluídos ou a eventos que o Jira não disponibiliza, nem garante um snapshot se o
projeto mudar durante a coleta. A conferência dos casos e a reconstrução das
métricas são verificados separadamente; esta ferramenta de prova não substitui a sincronização do dashboard.

Para preparar os exemplos de conferência do quarto item, sem nova consulta ao
Jira, use o relatório completo do terceiro item. Para o ZUR, os tipos, status finais
e colunas de trabalho abaixo foram confirmados pelo usuário para essa conferência:

```bash
uv run python -m app.jira_review \
  --input .local/jira-probe-step-3.json \
  --output .local/jira-review-step-4.json \
  --project 1 \
  --task-type 3 --task-type 5 --bug-type 10945 \
  --task-final-status 10203 --task-final-status 5 \
  --bug-final-status 10203 --bug-final-status 5 \
  --work-status 3 --work-status 14439 --work-status 14440 \
  --work-status 14441 --work-status 14442
```

Para gerar a evidência final, use `--output .local/jira-phase1-review.json` no
comando acima. Esses parâmetros são temporários: tarefas dos tipos Tarefa/Subtarefa, bugs do tipo
BugV2, status finais Concluído/Resolvido e as cinco colunas entre Em Progresso e
ITENS REPROVADOS como trabalho. A ferramenta não salva configuração de projeto,
não lê o `.env` e não acessa a rede. Para outros projetos, forneça as escolhas
confirmadas para seus próprios metadados; os IDs não são universais.

O relatório seleciona até três exemplos de cada caso (`--examples` aceita de 1 a
20), registra as regras usadas e o SHA-256 da coleta de origem. Os exemplos
contêm chaves, referências aos eventos e datas somente no arquivo local, com
permissão `600`; o terminal mostra apenas contagens agregadas. Não use o mesmo
caminho para a coleta e a conferência.

As categorias distinguem múltiplas sprints, remoções explícitas, subtarefas,
primeiras entradas observadas em status final, novas conclusões após reabertura,
transições entre status finais e bugs reabertos. Uma história descontínua, um
status atual incompatível ou uma conclusão sem transição disponível impedem
classificar uma primeira conclusão como candidata verificável. Histórias e épicos
ficam fora do escopo dessa seleção pelas regras fornecidas.

Exemplos candidatos de trabalho carregado exigem participação explícita em duas
sprints consecutivas, entrada em trabalho e estado não final nas referências.
A versão atual usa `startDate`, `completeDate` nas encerradas e o instante da
coleta nas ativas, com limites `[início, fim)` e datas normalizadas em UTC. Pares
sobrepostos são preservados nas janelas, mas ficam fora da seleção de exemplos
de trabalho carregado. Múltiplas sprints, isoladamente, não comprovam esse caso.
O relatório inicial da etapa 4 usava datas planejadas exploratórias; gere uma
nova conferência para aplicar as regras aprovadas.

Subtarefas distinguem associação atual, histórico próprio e informação
indisponível. A tarefa mãe aparece apenas para comparação, sem atribuir sua
participação histórica à subtarefa. `candidate_count` é uma contagem de tickets
com evidência para inspeção, não um indicador por sprint; as categorias podem se
sobrepor e não devem ser somadas. Uma contagem zero significa apenas que essa
seleção não encontrou um exemplo nos dados disponíveis.

A geração desse arquivo seleciona exemplos, sem conferir novamente a API. Os
sinalizadores `manual_review_complete` e `phase_1_complete` permanecem `false`
nessa seleção. A conferência técnica direta e a consolidação abaixo registram
separadamente os critérios efetivamente verificados. Revisão manual pela interface
não é apresentada como realizada. Lacunas ficam em `gaps` e `limitations`.

Para conferir os eventos selecionados diretamente no Jira e buscar os históricos
de vínculo/tipo das subtarefas e seus pais atuais:

```bash
uv run python -m app.jira_history_check \
  --input .local/jira-probe-step-3.json \
  --review .local/jira-phase1-review.json \
  --output .local/jira-history-check-v2.json --project 1
```

Use no argumento `--review` o caminho da nova conferência gerada com o comando
anterior e a política de datas atual. O nome `jira-phase1-review.json` identifica
a evidência final do ZUR. Essa consulta usa somente GET, lê a conexão das variáveis de ambiente `JIRA_PROBE_1_URL`, `JIRA_PROBE_1_EMAIL` e `JIRA_PROBE_1_TOKEN` (prefixo `JIRA_PROBE_2_` para a segunda conexão),
não imprime identificadores ou conteúdo privado e pode levar alguns minutos.

Para completar pais históricos presentes na coleta e evitar reler tickets já
conferidos, faça uma segunda execução com `--resume-from`, usando outro destino:

```bash
uv run python -m app.jira_history_check \
  --input .local/jira-probe-step-3.json \
  --review .local/jira-phase1-review.json \
  --resume-from .local/jira-history-check-v2.json \
  --output .local/jira-history-check-complete.json --project 1
```

Para verificar também os status e sprints históricos ausentes da configuração
atual, acrescente `--historical-metadata` usando como origem a conferência
completa e um destino próprio:

```bash
uv run python -m app.jira_history_check \
  --input .local/jira-probe-step-3.json \
  --review .local/jira-phase1-review.json \
  --resume-from .local/jira-history-check-complete.json \
  --historical-metadata \
  --output .local/jira-history-check-with-metadata.json --project 1
```

O reuso exige a mesma impressão digital de coleta e uma conferência anterior
válida. A data das verificações reutilizadas fica registrada. Eventos de vínculo
usam `IssueParentAssociation`, além do formato legado; mudanças de tipo também
são preservadas nas novas coletas. Dados de origem que divergirem da API impedem
marcar a conferência como verificada.

A consolidação é local e não acessa a rede:

```bash
uv run python -m app.jira_phase1 \
  --input .local/jira-probe-step-3.json \
  --review .local/jira-phase1-review.json \
  --checks .local/jira-history-check-with-metadata.json \
  --output .local/jira-phase1-proposal.json --project 1
```

A consolidação retorna código `2` enquanto houver critérios pendentes. Para
reproduzir o encerramento do ZUR, use os IDs já confirmados na análise e gere o
relatório final:

```bash
uv run python -m app.jira_phase1 \
  --input .local/jira-probe-step-3.json \
  --review .local/jira-phase1-review.json \
  --checks .local/jira-history-check-with-metadata.json \
  --output .local/jira-phase1.json --project 1 \
  --use-confirmed-status-rules
```

`--use-confirmed-status-rules` registra o uso dos IDs previamente confirmados pelo
usuário para a conferência, sem cadastrar configurações do produto. O método das
subtarefas só é considerado verificado se os históricos sustentarem toda a
participação reconstruída nessa coleta; lacunas mantêm o critério pendente.
Erros retornam `1`; `0` indica os critérios técnicos completos para o projeto
selecionado, sem certificar o segundo projeto ou a primeira versão inteira.

A prova de subtarefas cruza seus períodos de existência, tipo e vínculo pai com a
participação histórica da mãe e os intervalos da sprint. Não copia sprints
anteriores à criação da subtarefa nem atribui status/conclusões da mãe. Vínculo
explicitamente nulo é separado de pai ou histórico indisponível. Esses resultados
são evidência de viabilidade, sem calcular os indicadores do produto.

Todos os relatórios permanecem locais, com permissão `600`. O plano registra as
regras de datas, as decisões e as limitações; datas ausentes, metadados históricos
indisponíveis e lacunas não são convertidos em zero.

Uma leitura bem-sucedida não comprova histórico completo: permissões podem ocultar
tickets e eventos. O modo padrão consulta uma amostra por projeto; mesmo
`--all-issues` ainda não valida os casos das métricas. A fase 1 foi concluída para o ZUR; a validação do segundo projeto real foi
adiada pelo usuário e continua necessária antes de concluir a primeira versão. Sem tickets visíveis, o relatório indica que o changelog não foi
verificado. Falhas de autenticação, permissões ou coleta aparecem como falhas,
sem apresentar dados indisponíveis como zero.

A implementação segue a documentação oficial de
[autenticação com token](https://developer.atlassian.com/cloud/jira/platform/basic-auth-for-rest-apis/),
[busca de tickets](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/) e
[quadros do Jira Software](https://developer.atlassian.com/cloud/jira/software/rest/api-group-board/),
[campos](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-fields/) e
[changelogs dos tickets](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-changelog-get).

Para verificar a prova sem credenciais ou acesso à rede:

```bash
cd apps/api
uv run python -m unittest discover -s tests -v
```
