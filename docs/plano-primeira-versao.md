# Plano da primeira versão — Hub de projetos e métricas

Status: escopo aprovado em 23/11/2026.

## Objetivo

Criar um hub local para acompanhar a evolução do volume de entregas e dos bugs ao longo das sprints, com um marco de adoção de inteligência artificial (IA) por projeto.

A análise deve permitir observar mudanças associadas ao período de adoção de IA. Os indicadores, isoladamente, não demonstram causalidade nem medem produtividade individual.

## Escopo aprovado

- Suportar dois projetos desde a primeira versão, com análises isoladas.
- Integrar com Jira Cloud somente para leitura.
- Cadastrar URL e credenciais próprias para cada projeto.
- Usar um quadro do Jira por projeto.
- Executar localmente, sem tela de login, com acesso restrito à própria máquina.
- Proteger as credenciais armazenadas localmente, sem expô-las nos dashboards ou logs.
- Sincronizar somente por solicitação do usuário.
- Recuperar todo o histórico disponível de cada projeto; os projetos atuais têm menos de um ano.
- Analisar inicialmente por sprint.
- Contar cada tarefa e subtarefa com peso um.
- Excluir histórias e épicos das contagens.

## Configuração por projeto

O cadastro deve permitir:

- Identificar o projeto e configurar sua conexão com o Jira Cloud.
- Selecionar um quadro e suas sprints.
- Selecionar os tipos que representam tarefas, subtarefas e bugs.
- Selecionar as colunas de trabalho.
- Selecionar um ou mais status finais, com regras próprias para tarefas e bugs.
- Registrar a data de adoção de IA.

As opções de tipos, colunas e status devem ser obtidas do Jira, sem depender de nomes fixos como “Done” ou “Em andamento”.

## Regras das métricas

### Tarefas e subtarefas trabalhadas

Uma tarefa ou subtarefa entra na contagem da sprint quando pertenceu a ela e passou por uma das colunas de trabalho configuradas.

O trabalho iniciado anteriormente continua aparecendo enquanto não atingir um status final, desde que o ticket pertença à sprint analisada. Não é necessário haver uma nova movimentação em cada sprint para que um trabalho ainda não resolvido continue visível.

Regras de contagem:

- Cada tarefa e cada subtarefa valem uma unidade, inclusive quando a tarefa é mãe de subtarefas também contabilizadas.
- Cada ticket conta no máximo uma vez por sprint.
- Um ticket pode aparecer em várias sprints.
- Tickets removidos da sprint também entram quando atenderam aos critérios durante sua participação nela.
- Uma pendência só entra na sprint seguinte se tiver pertencido a ela no Jira; não existe inclusão automática apenas por continuar aberta.
- A conclusão retira o ticket das pendências, mas preserva sua participação nos resultados históricos.

### Entregas concluídas

Contar a primeira conclusão de cada tarefa ou subtarefa, conforme os status finais selecionados para o projeto.

- Passar entre dois status finais não gera outra entrega.
- Reabrir e concluir novamente o mesmo ticket não gera outra entrega.
- O ticket reaberto pode voltar a contar como trabalhado em outra sprint quando cumprir os critérios de participação e trabalho.
- Reaberturas devem ser apresentadas separadamente das primeiras conclusões.

### Bugs totais

Contar todos os bugs do projeto que estiveram abertos em algum momento do intervalo da sprint, independentemente de terem pertencido a ela.

- Incluir bugs criados antes da sprint e ainda abertos durante parte ou todo o intervalo.
- Incluir bugs criados e resolvidos dentro do intervalo.
- Incluir bugs antigos reabertos durante o intervalo.
- Contar cada bug uma única vez no total da sprint.
- Usar os status finais configurados para determinar quando o bug deixa de estar aberto.
- Não exigir vínculo entre bugs e entregas.

### Bugs novos e existentes

| Categoria | Regra |
| --- | --- |
| Novos | Criados dentro do intervalo da sprint. |
| Existentes | Criados antes do intervalo e que estiveram abertos em algum momento dele, incluindo reabertos. |

As categorias devem somar exatamente o total de bugs apresentado para a sprint.

### Proporção principal

**Bugs totais ÷ tarefas e subtarefas trabalhadas.**

Apresentar os valores absolutos junto da proporção e detalhar os bugs entre novos e existentes. Quando não houver tarefas ou subtarefas trabalhadas, mostrar “não calculável”.

Essa proporção relaciona o volume de bugs ao trabalho do período. Ela não representa a parcela de entregas que causou defeitos: bugs antigos podem aparecer em várias sprints, e não há vínculo obrigatório com as entregas.

## Dashboard por projeto

- Seleção de sprints.
- Totais de tarefas e subtarefas trabalhadas, entregas concluídas e bugs.
- Separação de bugs novos e existentes.
- Evolução dos indicadores e da proporção entre bugs e trabalho ao longo das sprints.
- Marco de adoção de IA.
- Identificação de sprints que atravessam a data de adoção como períodos de transição.
- Comparação entre sprints anteriores e posteriores à adoção, com totais e médias por sprint.
- Lista dos tickets que compõem cada número, para conferência dos resultados.
- Data e hora da última sincronização, andamento da coleta e eventuais falhas por projeto.

Os projetos permanecem isolados, sem ranking de produtividade ou equivalência presumida entre suas unidades de trabalho.

## Sincronização e histórico

A primeira sincronização manual deve buscar todo o histórico disponível do projeto. As seguintes devem buscar mudanças e atualizar os dados locais sem duplicar registros.

A coleta deve permitir reconstruir participação em sprints, passagem por colunas de trabalho, status finais, reaberturas e primeira conclusão. Isso deve ser validado tecnicamente antes da construção dos indicadores.

Lacunas no histórico ou limitações de acesso devem aparecer explicitamente. Informação indisponível não pode ser apresentada como zero nem como ausência de atividade.

## Fases de implementação

O progresso de cada fase está registrado nos checklists e nas evidências abaixo. A sequência mantém o escopo aprovado e aproveita a base existente: API em Python/FastAPI e frontend em React/TypeScript/Vite.

| Fase | Resultado principal | Depende de |
| --- | --- | --- |
| 1. Viabilidade do histórico | Evidências de que os dados sustentam as métricas | Acesso de leitura ao projeto no escopo da validação atual |
| 2. Base local e persistência | Aplicação preparada para armazenar dados e proteger credenciais | Fase 1 |
| 3. Cadastro e configuração | Dois projetos configuráveis com suas próprias regras | Fase 2 |
| 4. Sincronização manual | Histórico coletado, atualizado e rastreável | Fase 3 |
| 5. Motor de métricas | Indicadores calculados e conferíveis por sprint | Fase 4 |
| 6. Dashboards e análise de IA | Fluxo completo de consulta e comparação | Fase 5 |
| 7. Validação da primeira versão | Uso local validado com os dois projetos reais | Fase 6 |

### Fase 1 — Validar a viabilidade do histórico do Jira

**Objetivo:** confirmar a disponibilidade dos dados antes de construir indicadores que dependem deles.

**Escopo de validação atualizado pelo usuário em 23/11/2026:** concluir esta fase somente com o ZUR (conexão 1). O segundo projeto fica adiado e continua necessário na validação da primeira versão. Os checklists desta fase se referem ao ZUR; não certificam o segundo projeto.

Entregas:

- [x] Fazer uma prova de integração somente de leitura no projeto do escopo atual (ZUR), sem versionar segredos; segundo projeto adiado pelo usuário.
- [x] Verificar obtenção de projetos, quadro, colunas, status, tipos de tickets, sprints e histórico dos tickets.
- [x] Validar recuperação paginada de todo o histórico necessário, incluindo mudanças de status e de participação em sprints.
- [x] Conferir exemplos de tarefas carregadas entre sprints, tickets removidos, subtarefas, primeiras conclusões e bugs reabertos.
- [x] Verificar como identificar participação de subtarefas quando a associação à sprint não estiver explícita; documentar a evidência e não presumir herança da tarefa mãe.
- [x] Definir e registrar o uso de datas de início/fim das sprints, o tratamento da sprint em andamento, o fuso horário e os limites dos intervalos.
- [x] Registrar limitações de permissões e de histórico, além da correspondência entre colunas e status. Identificar mudanças históricas de configuração que não possam ser reconstruídas.

**Andamento (23/11/2026):** prova manual de leitura (`app.jira_probe`) executada com sucesso no projeto ZUR, quadro 3040. A configuração temporária usa variáveis de ambiente e o `.env` local, com `.env.example` sem segredos; a configuração definitiva permanece no cadastro da fase 3. O projeto 1 é o padrão; `--all-projects` solicita ambas as conexões.

No segundo item, a execução real leu 7 colunas, 5 tipos com seus status, 20 sprints (encerradas, em andamento e futuras) e uma amostra de 5 tickets. O campo Sprint foi identificado pelo schema como `customfield_10005`. O relatório local `apps/api/.local/jira-probe-step-2.json` contém datas das sprints e eventos de status/sprint da amostra. Foram obtidos 8, 21, 21, 19 e 18 eventos históricos, respectivamente, para ZUR-5, ZUR-33, ZUR-65, ZUR-64 e ZUR-67; todos apresentam mudanças de status e sprint. Os 5 tickets são do tipo Tarefa, portanto essa amostra ainda não confere subtarefas ou bugs. As verificações automatizadas não usam credenciais reais.

No terceiro item, a prova foi ampliada com `--all-issues` e executada no ZUR com páginas de 20 itens, sem filtro de quadro, tipo ou sprint. A busca percorreu 50 páginas e retornou 1.000 tickets distintos. Foram lidas 1.214 páginas de changelog, com 14.591 eventos históricos; 203 tickets exigiram mais de uma página. Todos os contadores de término foram conferidos, sem falhas nem tickets pendentes de leitura. Foram exportadas 3.674 mudanças de status e 1.479 mudanças de sprint. Como exemplo de paginação real, ZUR-33 e ZUR-65 retornaram 21 eventos em 2 páginas cada. O relatório local `apps/api/.local/jira-probe-step-3.json` registra a auditoria de cada consulta, permanece fora do Git e tem permissão de acesso `600`.

A coleta retornou 440 tickets do tipo Tarefa, 328 Subtarefa, 110 BugV2, 108 História e 14 Epic. Esses números descrevem os registros lidos, não indicadores calculados; histórias e épicos continuam excluídos das futuras contagens das métricas. A presença de subtarefas e bugs nessa coleta ainda não confere participação em sprints, primeiras conclusões ou reaberturas. Os testes automatizados da prova somam 27 casos, incluindo múltiplas páginas, falhas parciais, cursor repetido e totais inconsistentes.

No quarto item, foi implementada a conferência local `app.jira_review`, sem novas consultas ao Jira. O usuário confirmou temporariamente Tarefa (3) e Subtarefa (5) como trabalho, BugV2 (10945) como bug, status finais 10203/5 para ambos e os status de trabalho 3/14439/14440/14441/14442 (as cinco colunas entre Em Progresso e ITENS REPROVADOS). Essas escolhas ficam registradas na evidência e não substituem o cadastro da fase 3.

A análise local selecionou exemplos candidatos entre 878 tickets dos tipos aprovados: 131 com evidências exploratórias de trabalho carregado, 532 com múltiplas sprints, 115 com remoção explícita, 580 com primeira entrada observada em status final, 3 bugs com reabertura, 14 tarefas/subtarefas com novas conclusões após reabertura e 37 com transições entre status finais. São quantidades de tickets candidatos à conferência, não métricas por sprint; as categorias se sobrepõem. O relatório `apps/api/.local/jira-review-step-4.json` contém exemplos e referências aos eventos apenas localmente, regras provisórias, impressão digital da coleta e limitações. A conferência manual no Jira continua pendente; os sinalizadores de conclusão permanecem falsos. Os testes automatizados da coleta e da conferência somam 43 casos.

**Limitação identificada para o quinto item:** das 328 subtarefas, 7 possuem mudanças próprias de sprint no histórico e 321 não possuem. Há 264 com valor atual de sprint e 64 sem esse valor; o campo foi retornado nas 328. O valor atual e a participação da tarefa mãe não demonstram a associação histórica da subtarefa. Nenhuma herança foi presumida. É necessário verificar a evidência disponível no Jira e resolver essa limitação ou apresentá-la para decisão antes de implementar a reconstrução correspondente.

Os exemplos de trabalho carregado usam datas planejadas somente como referência exploratória, exigem associação explícita às duas sprints e não definem a regra definitiva dos intervalos. Sobreposições, datas efetivas e eventos exatamente nos limites continuam pendentes do sexto item. Nenhum indicador foi implementado nesta conferência.

**Conferência técnica final no ZUR:** os exemplos selecionados foram comparados diretamente aos eventos e campos da API de leitura do Jira, sem divergências. A verificação incluiu 425 tickets (subtarefas, pais atuais/históricos e exemplos), com 386 eventos de associação pai e 30 mudanças de tipo. A suíte de verificações da fase soma 69 testes aprovados; a conferência de segredos encontrou zero valores de token nos arquivos versionáveis, e o `.env` está ignorado e com permissão `600`. Os históricos relidos coincidem com a coleta de origem e a permissão de navegação e o mapeamento atual de colunas foram conferidos. O relatório `apps/api/.local/jira-history-check-with-metadata.json` registra a evidência completa e a checagem adicional dos metadados históricos. A comparação técnica direta atende à conferência dos exemplos; revisão manual pela interface não foi executada nem é apresentada como executada.

O campo `IssueParentAssociation` é a fonte documentada de mudanças de pai no Jira Cloud. A projeção da coleta agora preserva esse campo e as mudanças de tipo, além de status e sprint. A prova da participação usa o vínculo vigente, a existência e o tipo de cada subtarefa, a participação histórica do pai e a interseção com as datas da sprint. Não copia sprints anteriores à criação da subtarefa, não usa apenas o pai atual e não herda status ou conclusões. Períodos explicitamente sem pai ficam separados de informação desconhecida. A proposta conseguiu reconstruir as 328 subtarefas sem lacunas de vínculo nessa coleta, com 1.069 segmentos de intervalo; segmentos não são tickets nem métricas e não devem ser somados como entregas. A limitação inicial foi resolvida tecnicamente para esta coleta pela documentação oficial e pelos vínculos históricos verificados. A derivação é evidência de viabilidade, sem cadastrar configurações do produto. A consolidação final está em `apps/api/.local/jira-phase1.json`; a proposta anterior permanece como evidência intermediária.

**Confirmação explícita do usuário em 23/11/2026:** adotado para o ZUR o método documentado de participação das subtarefas, com pais históricos, conversões de tipo e data de criação; qualquer lacuna futura permanece indisponível. Confirmada também a aplicação dos IDs de trabalho e conclusão já escolhidos a todo o histórico, mantendo a configuração antiga de colunas como não reconstruída e sprints sem metadados como indisponíveis, sem presumir datas ou colunas. Essas decisões valem para a conferência desta fase; o cadastro definitivo permanece na fase 3.

**Regras de datas aprovadas pelo usuário em 23/11/2026:**

- Início: `startDate` informado pelo Jira.
- Sprint encerrada: fim em `completeDate`, sem substituir por `endDate` quando ausente.
- Sprint ativa: fim no instante fixo da coleta (`collection.finished_at`), inclusive quando ultrapassa o fim planejado; resultado parcial.
- Sprint futura: sem intervalo de análise ou indicadores, identificada como não iniciada.
- Limites: `[início, fim)`. Um evento no início pertence ao intervalo; um evento no fim não pertence a ele. Não se inclui automaticamente um ticket na sprint seguinte: a participação continua obrigatória.
- Armazenamento e comparação de instantes em UTC; exibição em `America/Sao_Paulo`. Datas sem fuso, ausentes, incoerentes ou posteriores ao corte produzem informação indisponível.
- Sprints sobrepostas conservam seus próprios intervalos, sem truncamento nem redistribuição de eventos. São 9 pares sobrepostos nessa coleta, dos quais 5 são pares consecutivos por início.
- `endDate` permanece referência planejada. As 17 sprints encerradas têm `completeDate` diferente do fim planejado; uma das 2 ativas já ultrapassava `endDate` no corte.

As 20 sprints produziram 19 intervalos disponíveis (17 encerradas e 2 ativas) e 1 futura sem intervalo de análise. As convenções foram implementadas em `app.jira_time`, testadas e aplicadas à nova conferência `apps/api/.local/jira-phase1-review.json`; os 136 candidatos de trabalho carregado dessa versão usam datas efetivas e pares não sobrepostos para seleção de exemplos. Isso não é cálculo de tarefas trabalhadas por sprint.

**Permissões, metadados e limites históricos:**

- Autenticação, navegação no projeto e leituras de quadro, tipos/status, campos, sprints e changelogs foram verificadas. Somente GET é usado; nenhuma escrita no Jira foi executada.
- A configuração atual do quadro corresponde à da coleta: Para Fazer → 10202; Em Progresso → 3; ITENS EM REVISÃO → 14439; ITENS LIBERADOS PARA TESTE → 14440; ITENS EM TESTE → 14441; ITENS REPROVADOS → 14442; Concluído → 10203 e 5.
- Há 13 IDs de status observados fora das colunas atuais, dos quais 8 também não aparecem nos tipos atuais, além de referências a 16 sprints não retornadas pelo quadro. Os identificadores completos ficam apenas no relatório local.
- A configuração histórica de colunas/status não foi reconstruída. Não se pode presumir que os status antigos pertenciam às colunas atuais. Na conferência, os IDs de trabalho e conclusão previamente confirmados pelo usuário são aplicados a todo o histórico como regra de análise explícita, sem inventar configurações anteriores. Essa aplicação já integra a análise dos exemplos com os parâmetros escolhidos e não cadastra novas regras de produção.
- A consulta direta recuperou metadados de 14 das 16 sprints ausentes da listagem, todas criadas em outros quadros. Isso não as inclui automaticamente no quadro selecionado nem amplia o escopo para múltiplos quadros. Duas sprints e os 8 status ausentes dos tipos atuais não foram recuperados por essa credencial. Sprints sem metadados permanecem indisponíveis; suas datas ou associação ao quadro não são presumidas.
- Permissão de navegação não comprova visibilidade de todos os tickets ou eventos. Tickets ocultos, excluídos, movidos para fora do projeto e dados não disponibilizados pelo Jira podem escapar à coleta. A coleta não é um snapshot transacional.
- Mudanças futuras de metadados e regras devem preservar a evidência de origem e a configuração de cálculo; nenhuma configuração anterior será inventada retroativamente.

**Como os dados sustentam os indicadores futuros:**

| Indicador | Reconstrução sustentada pelas evidências |
| --- | --- |
| Tarefas e subtarefas trabalhadas | Cruzar participação registrada na sprint com períodos de trabalho próprios do ticket. Trabalho iniciado anteriormente permanece elegível até um status final, durante sua participação. Cada ID conta uma vez por sprint; mãe e filhas são IDs independentes e valem uma unidade cada. Para subtarefas, a participação derivada usa a política documentada expressamente aprovada pelo usuário, sem herdar status ou trabalho da mãe. |
| Primeiras conclusões | Ordenar as transições de status por instante, localizar a primeira entrada nos status finais selecionados e preservar esse único evento global, com data e participação para conferência por sprint. Passagens entre finais e conclusões posteriores não criam outra primeira conclusão. Ausência de evidência suficiente permanece identificada. |
| Reaberturas | Identificar transições de um status final para um não final e manter seus eventos separados da primeira conclusão. O retorno ao trabalho requer os critérios próprios de participação e trabalho. |
| Bugs totais | Reconstruir os períodos abertos desde a criação e após reaberturas, usando os status finais próprios de bugs. Cruzar os períodos abertos com o intervalo da sprint, sem exigir associação à sprint ou ao quadro. Deduplicar o bug dentro da sprint. |
| Bugs novos e existentes | Dentro dos bugs incluídos pelo critério de abertura, separar a criação no intervalo da sprint da criação anterior a ele. As categorias são exclusivas e devem somar o total. |
| Proporção principal | Dividir bugs totais por tarefas/subtarefas trabalhadas, preservando os absolutos. Denominador zero produz “não calculável”; informação indisponível produz limitação de completude, sem substituição por zero. |

As tabelas explicam a viabilidade com os eventos conferidos; os cálculos de domínio pertencem à fase 5. As janelas temporais e os exemplos já podem ser reproduzidos pelas ferramentas da fase 1.

Fontes oficiais usadas para conferir o comportamento e os formatos: [subtarefas no Jira Cloud](https://support.atlassian.com/jira-software-cloud/docs/create-a-work-item-and-a-subtask/), [histórico de vínculo pai](https://developer.atlassian.com/cloud/jira/platform/deprecation-notice-issue-reparenting-changelogs/), [datas de sprint](https://developer.atlassian.com/cloud/jira/platform/jira-expressions-type-reference/#sprint), [configuração de quadro](https://developer.atlassian.com/cloud/jira/software/rest/api-group-board/) e [consulta de status](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-workflow-statuses/).

**Conclusão da fase 1 no escopo atual:** os sete critérios técnicos estão atendidos no ZUR, conforme `apps/api/.local/jira-phase1.json` (`phase_1_complete_for_selected_project: true`). Foram conferidos os exemplos diretamente na API, verificada a derivação documentada das subtarefas, aplicadas as datas aprovadas e registradas as limitações históricas e de acesso. A conferência usa os IDs já confirmados pelo usuário; o cadastro definitivo permanece na fase 3. A validação do segundo projeto foi adiada expressamente pelo usuário e continua necessária para a primeira versão. Nenhum critério de aceitação das fases posteriores foi marcado por esta conclusão.

**Critério de conclusão:** conseguir explicar, com exemplos conferidos, como reconstruir cada indicador no projeto do escopo atual (ZUR, por orientação do usuário; segundo projeto adiado). Uma limitação que impeça uma regra aprovada deve ser resolvida ou apresentada para decisão antes de implementar essa regra; nunca substituída silenciosamente por uma aproximação.

### Fase 2 — Preparar a base local e a persistência

**Objetivo:** estabelecer armazenamento e organização técnica para suportar cadastro, coleta e cálculo.

Entregas:

- [x] Separar na API as responsabilidades de integração com Jira, persistência, sincronização e métricas.
- [x] Definir o banco local e a estratégia de evolução do esquema. SQLite é a opção inicial proposta, a confirmar nesta fase.
- [x] Modelar projetos, conexões, regras de classificação, quadro, sprints, tickets, eventos históricos e execuções de sincronização.
- [x] Usar identificadores do Jira associados ao projeto/conexão para impedir mistura de dados entre projetos.
- [x] Definir armazenamento protegido de credenciais, mantendo material de proteção separado dos dados protegidos; excluir segredos e dados locais do controle de versão.
- [x] Garantir que credenciais não sejam devolvidas ao frontend após o cadastro nem registradas em logs.
- [x] Preparar execução restrita à máquina local, incluindo configuração de portas do ambiente de desenvolvimento.
- [x] Preparar a estrutura de testes das regras de domínio e da integração, sem depender de credenciais reais na execução automatizada.

**Critério de conclusão:** dados de projetos persistem após reiniciar a aplicação, permanecem isolados e podem ser recuperados pela API; o mecanismo de proteção das credenciais e a execução local estão definidos e verificados.

**Conclusão verificada em 23/11/2026:** SQLite adotado com migrações transacionais versionadas por `user_version`. O esquema contém projetos, conexões, configurações imutáveis por versão, metadados de quadro, sprints, tickets, eventos, execuções de sincronização e resultados vinculados à configuração. As chaves externas são compostas por projeto e ID Jira. A API foi organizada em integração, persistência, domínio e serviço de cadastro; os módulos de sincronização e métricas ficam reservados às fases 4 e 5, sem executar coleta ou cálculo nesta fase.

E-mail e token são criptografados com Fernet. A chave fica em `~/.config/echiro/credentials.key`, separada do banco `apps/api/.local/echiro.sqlite3` e fora do repositório. Ambos usam permissão `600`. Perda da chave não dispara substituição silenciosa. Credenciais não aparecem nas respostas da API, inclusive nos erros de validação. API e Vite escutam em `127.0.0.1`; cliente, Host e origem do navegador são validados, e o encaminhamento do Dev Container permanece local.

A persistência após reinício, o isolamento de duas conexões, a integridade das chaves compostas, as transações, a proteção das credenciais e as restrições de acesso foram verificados com banco e chave temporários. A documentação de execução e backup está no README.

### Fase 3 — Implementar cadastro e configuração dos projetos

**Objetivo:** permitir preparar os dois projetos pela interface, sem editar código.

Entregas:

- [x] Criar listagem, cadastro e edição dos projetos, cada um com sua URL e credenciais.
- [x] Implementar teste de conexão e mensagens compreensíveis para falhas de autenticação, permissão ou comunicação.
- [x] Buscar metadados do Jira por ação do usuário para escolher um quadro, tipos de tickets, colunas de trabalho e status finais.
- [x] Permitir múltiplas seleções e regras finais próprias para tarefas e bugs.
- [x] Registrar a data de adoção de IA.
- [x] Validar configurações incompletas ou conflitantes, como um tipo classificado simultaneamente como tarefa e bug.
- [x] Definir que alterações nas regras exigem recálculo dos indicadores e identificar resultados ainda calculados com configuração anterior.

**Critério de conclusão:** cadastrar e configurar os dois projetos com credenciais independentes; as escolhas persistem e nenhum projeto consulta ou altera a configuração do outro.

**Conclusão verificada em 23/11/2026:** a interface oferece listagem, cadastro, edição de nome/credenciais, teste de conexão, busca manual de metadados e configuração de quadro Scrum, tipos, colunas, status finais próprios, sprints e data de adoção de IA. URL e chave identificam a origem e permanecem fixas após o cadastro; outra origem requer um novo projeto, preservando o isolamento do histórico. Os IDs e nomes das opções vêm do Jira. Configurações incompletas, tipos sobrepostos, status incompatíveis e seleções de outro quadro/projeto são recusados.

Mudanças efetivas das regras ou da data de IA geram versões imutáveis. Resultados possuem versão de origem e a API distingue ausência de cálculo, resultado atual e necessidade de recálculo; a interface sinaliza resultados antigos. O cálculo e sua execução permanecem na fase 5. Salvar seleções equivalentes, inclusive em outra ordem, não cria nova versão.

O critério funcional de duas conexões foi verificado com dois projetos simulados independentes, pela API e pelo navegador Chromium: cadastro, configuração, alteração, recarregamento e preservação das escolhas, sem mistura entre projetos. A execução móvel não apresentou transbordamento horizontal nem erros JavaScript. A suíte completa soma 85 testes aprovados e o build do frontend passou.

No ambiente de uso foi cadastrado somente o ZUR, usando as credenciais locais existentes, os tipos/status/colunas aprovados e as 20 sprints obtidas por consulta real de leitura. O teste de conexão real passou. A data de adoção de IA permanece em branco até ser conhecida. O segundo projeto real segue adiado pelo usuário; sua validação continua pendente para a primeira versão, sem impedir a entrega do cadastro com suporte a ambas as conexões. Nenhum projeto simulado foi incluído no banco de uso. Evidência agregada: `apps/api/.local/phase-2-3-verification.json`.

**Escopo de execução mantido para as fases seguintes:** por orientação do usuário, avançar autonomamente com o ZUR e manter o segundo projeto real adiado. As fases 4 a 6 são concluídas no escopo atual com execução real no ZUR e verificação funcional de duas conexões independentes simuladas. A validação de ponta a ponta do segundo projeto real continua explicitamente pendente na fase 7; os testes simulados não a substituem.

### Fase 4 — Implementar a sincronização manual do histórico

**Objetivo:** construir uma base local completa e atualizável, com execução explícita pelo usuário.

Entregas:

- [x] Implementar a coleta inicial de todo o histórico disponível do projeto, incluindo bugs que não pertencem ao quadro ou às sprints selecionadas.
- [x] Coletar tickets, sprints e eventos necessários para reconstrução temporal, percorrendo todas as páginas de resultados.
- [x] Implementar atualizações incrementais e tratamento de falhas, com tentativas controladas e respeito aos limites de requisição encontrados na integração.
- [x] Usar gravações idempotentes e pontos de retomada para evitar duplicidade ou perda de dados em nova execução.
- [x] Impedir execuções concorrentes conflitantes para o mesmo projeto.
- [x] Exibir estados de execução, progresso disponível, última sincronização bem-sucedida e erros por projeto.
- [x] Preservar a última base consistente em caso de falha e sinalizar atualização incompleta, sem apresentá-la como coleta concluída.
- [x] Registrar lacunas e alterações de metadados que afetem a configuração ou o cálculo.

**Critério de conclusão:** a coleta inicial funciona nos dois projetos; repetir a sincronização não duplica registros; uma execução interrompida pode ser retomada ou refeita sem corromper os dados; não há início automático ou agendamento.

**Conclusão no escopo atual (23/11/2026):** a sincronização manual foi implementada com execução em segundo plano, exclusão mútua por projeto, paginação validada, até três leituras simultâneas de históricos, tentativas limitadas para falhas transitórias e respeito ao `Retry-After`. A atualização incremental compara `updated` após percorrer a lista completa e relê somente os históricos novos ou alterados. O campo atual é conferido novamente após a leitura de cada histórico alterado.

A área de preparação fica isolada da última base publicada e permite retomar uma tentativa interrompida mediante nova solicitação. Reiniciar a aplicação não reinicia a coleta. A publicação ocorre em uma transação; chaves compostas impedem duplicação. Eventos previamente armazenados não são apagados se a API deixar de retorná-los. Perda de visibilidade ou mudanças de configuração são limitações explícitas.

No ZUR, a execução real publicou 1.000 tickets e 20 sprints. Uma segunda execução reaproveitou os 1.000 históricos, com zero grupos de eventos duplicados. A interrupção e retomada também foram exercitadas durante a coleta real. Testes simulados verificaram falha parcial, preservação da base anterior, retomada, concorrência, isolamento entre dois projetos, perda de eventos/visibilidade e limites de tentativas. A validação real do segundo projeto permanece na fase 7.

### Fase 5 — Implementar o motor de métricas por sprint

**Objetivo:** transformar o histórico em indicadores reproduzíveis, conforme as regras aprovadas.

Entregas:

- [x] Reconstruir os intervalos de participação em sprints e os estados de trabalho e conclusão de cada ticket.
- [x] Calcular tarefas e subtarefas trabalhadas, preservando trabalho iniciado antes e ainda não resolvido durante sua participação na sprint.
- [x] Contar cada ticket uma vez por sprint e cada primeira conclusão uma vez no histórico, separando reaberturas.
- [x] Calcular bugs que estiveram abertos em qualquer parte do intervalo, inclusive sem associação à sprint.
- [x] Separar bugs novos e existentes e calcular a proporção principal.
- [x] Retornar junto dos indicadores os tickets que sustentam cada contagem e eventuais limitações de completude.
- [x] Recalcular resultados após sincronizações e mudanças nas regras, preservando os eventos de origem.
- [x] Implementar testes de domínio para tarefas mães e subtarefas, mudanças de sprint, trabalho persistente, reaberturas, bugs criados e resolvidos no mesmo intervalo, limites de datas e denominador zero.

**Critério de conclusão:** os cálculos correspondem aos exemplos conferidos nos dois projetos; novos mais existentes equivalem aos bugs totais; nenhuma reabertura duplica uma primeira entrega; lacunas não são representadas como zero.

**Conclusão no escopo atual (23/11/2026):** o motor puro reconstrói tipo, status, trabalho e participação ao longo do tempo. Usa eventos próprios nos períodos de tarefa padrão e vínculos históricos nos períodos de subtarefa, sem herdar status ou conclusões. Trabalho iniciado persiste até status final durante a participação; remoções não apagam trabalho anterior, e reaberturas não duplicam a primeira entrega. Bugs são independentes de participação no quadro/sprint. Cada indicador inclui tickets e limitações, e a proporção distingue denominador zero de histórico indisponível. Resultados são vinculados à versão das regras, ao motor e à execução de sincronização.

A comparação com as evidências da fase 1 confirmou 6 participações de exemplos de trabalho carregado, 3 primeiras conclusões, 3 casos de bugs reabertos e todos os 1.069 intervalos documentados das subtarefas. Novos mais existentes equivalem ao total de bugs em todas as sprints calculáveis. Os testes de domínio incluem conversões de tipo, criação da subtarefa, troca de pai, trabalho persistente, transições entre finais, múltiplas conclusões, limites, sprints sobrepostas/ativas/futuras, denominador zero e lacunas.

**Correção da relevância das lacunas:** seis tickets não têm evidência própria de sprint nos períodos anteriores à conversão de tarefa padrão em subtarefa. Inicialmente o motor invalidava trabalho, entregas e reaberturas sempre que esse período cruzava uma sprint, mesmo sem atividade elegível. Essa propagação era excessiva e foi corrigida no motor versão 2: a lacuna só invalida trabalho quando há trabalho potencial no trecho desconhecido, primeira entrega quando seu evento ocorre nele, e reabertura quando seu evento ocorre nele. Uma participação conhecida que já comprova a contagem unitária de trabalho permanece válida. Não se presumem associações ausentes nem se muda a regra das métricas.

Na conferência detalhada dos cinco tickets indicados pelo usuário (ZUR-443, ZUR-445, ZUR-446, ZUR-447 e ZUR-468), todos estavam em Para Fazer (10202) durante o período desconhecido e nenhum tinha primeira conclusão nele. Portanto, aquela lacuna não impedia determinar os indicadores dessas sprints. Após o recálculo, trabalho, entregas e bugs estão disponíveis nas 19 sprints já iniciadas; a futura permanece sem indicadores. A indisponibilidade incorreta de oito sprints foi eliminada. Foram acrescentados testes de regressão para lacuna sem atividade, atividade conhecida após conversão na mesma sprint e atividade realmente incerta dentro da lacuna; a suíte passou com 119 testes.

### Fase 6 — Construir dashboards e comparação da adoção de IA

**Objetivo:** disponibilizar a análise por projeto com navegação até os tickets de origem.

Entregas:

- [x] Criar navegação entre os projetos e seleção de sprints.
- [x] Exibir totais de trabalhadas, entregues, reaberturas e bugs, além da proporção e da separação entre bugs novos e existentes.
- [x] Mostrar gráficos de evolução por sprint e tabelas de tickets acessíveis a partir dos indicadores.
- [x] Marcar a adoção de IA e identificar sprints anteriores, posteriores e de transição.
- [x] Apresentar totais e médias por sprint para os grupos anteriores e posteriores; manter sprints de transição identificadas separadamente e fora dessas médias.
- [x] Mostrar a quantidade de sprints em cada grupo e distinguir sprints em andamento das encerradas para evitar comparações apresentadas como equivalentes sem indicação.
- [x] Tratar estados sem dados, ausência de períodos antes/depois, proporção não calculável, sincronização em curso e histórico incompleto.
- [x] Manter visíveis a última sincronização e a configuração usada nos resultados.

**Critério de conclusão:** selecionar um projeto e suas sprints, entender os indicadores, abrir os tickets que explicam cada número e comparar os períodos de adoção sem misturar os projetos nem ocultar lacunas.

**Conclusão no escopo atual (23/11/2026):** o dashboard permite navegar entre projetos, selecionar sprints, alternar gráficos de volumes/proporção, abrir as listas de tickets e seus links no Jira, consultar eventos e filtrar chaves. Mostra status/progresso da sincronização, última publicação, corte temporal e configuração usada, mantendo a base anterior visível quando uma tentativa falha.

O marco de IA usa meia-noite em America/Sao_Paulo. Antes, depois e transição são classificados pelos intervalos efetivos; as comparações mostram totais e médias somente das sprints encerradas e completas selecionadas. Ativas, transição e incompletas são identificadas e excluídas das médias. A proporção agregada usa somas dos absolutos, e o produto não afirma causalidade ou produtividade individual.

O fluxo completo passou no Chromium com dois projetos simulados, cada um com cinco sprints (antes, depois, transição, ativa e futura), incluindo cadastro, configuração, sincronização solicitada na interface, detalhes/links de origem, recarregamento e isolamento. A visualização móvel não teve transbordamento horizontal ou erro JavaScript. Foram verificados estados sem base, seleção vazia, futuro e denominador zero. O fluxo real do ZUR e suas limitações permanecem no banco e nas evidências locais.

**Refinamento de interação verificado:** o gráfico agora mostra um tooltip compartilhado por sprint ao passar o mouse sobre a faixa correspondente, inclusive quando os pontos se sobrepõem. O conteúdo inclui nome, período, estado parcial, classificação de IA, trabalhadas, primeiras entregas, bugs totais/novos/existentes e proporção, preservando “Indisponível” e “Não calculável”. Tab e setas permitem navegar pelo teclado; Escape fecha o tooltip. Hover, teclado, modo de proporção e limites em tela pequena foram conferidos no Chromium, sem erros JavaScript; o build do frontend passou.

**Refinamento do filtro de sprints verificado:** a análise oferece os modos “Incluir selecionadas” e “Excluir selecionadas”. No primeiro, as marcações indicam as sprints que entram; no segundo, indicam as que ficam fora. Alternar o modo preserva o conjunto exibido, invertendo as marcações. As ações “Marcar todas” e “Desmarcar todas” seguem o modo ativo. Gráficos, totais, tabela e comparação de IA usam o mesmo conjunto filtrado, sem alterar a configuração salva ou consultar o Jira. Os dois modos, troca preservando resultados, ações em lote e tela pequena foram conferidos no Chromium; o build passou.

### Fase 7 — Validar e preparar o uso local da primeira versão

**Objetivo:** confirmar o funcionamento completo e documentar a operação cotidiana.

Entregas:

- [ ] Executar o fluxo completo nos dois projetos: cadastro, configuração, sincronização, dashboard e conferência dos tickets.
- [x] Conferir amostras de sprints encerradas e em andamento, incluindo casos de reabertura e trabalho carregado entre sprints quando disponíveis.
- [x] Validar reinício da aplicação, nova sincronização, mudança de regras e recuperação de falhas de rede ou credenciais.
- [x] Conferir que a integração não realiza escritas no Jira e que segredos não aparecem em respostas, logs ou arquivos versionados.
- [x] Rodar os testes das métricas, verificações da API e build do frontend.
- [x] Documentar instalação, execução local, configuração das credenciais, sincronização, localização dos dados, cópia de segurança e limitações conhecidas.
- [ ] Conferir todos os critérios de aceitação deste plano.

**Critério de conclusão:** os dois projetos podem ser acompanhados localmente de ponta a ponta, os critérios de aceitação estão atendidos e as limitações encontradas estão documentadas.

**Validação realizada (23/11/2026):** 116 testes automatizados aprovados, build TypeScript/Vite concluído e fluxo de dois projetos simulados conferido no Chromium. No ZUR foram verificadas coleta inicial, interrupção/retomada, repetição incremental, cálculo, comparação com evidências anteriores e persistência dos resultados após reinício. Mudança de regras, falhas de rede/credenciais, preservação da base, recuperação e isolamento foram cobertos pelos testes. O cliente Jira usa exclusivamente GET; erros de validação não refletem credenciais, e a varredura dos arquivos versionáveis encontrou zero tokens reais. Dados, evidências e chave continuam fora do Git, com acesso restrito.

Evidências protegidas: `apps/api/.local/first-version-validation.json` (conferência agregada) e `apps/api/.local/first-version-dashboard.json` (resultados e tickets de origem). O README documenta operação, retomada, cálculo, backup e limitações. Nenhuma data de IA foi inventada: a análise usa o valor salvo na configuração do projeto.

**Pendência para concluir a fase 7:** executar e conferir o segundo projeto real, adiado pelo usuário. A fase e a liberação integral da primeira versão permanecem abertas. As limitações verificadas no ZUR estão documentadas e visíveis, sem substituição por zero. O suporte de ponta a ponta a duas conexões foi verificado com dados simulados, mas não certifica o acesso nem o histórico do segundo projeto real.

### Acompanhamento das fases

Marcar cada entrega após a verificação e a fase inteira somente quando seu critério de conclusão também estiver atendido.

- [x] Fase 1 — Viabilidade do histórico validada no ZUR; segundo projeto adiado por orientação do usuário.
- [x] Fase 2 — Base local e persistência verificadas.
- [x] Fase 3 — Cadastro e configuração disponíveis; isolamento verificado com duas conexões simuladas e ZUR real cadastrado.
- [x] Fase 4 — Sincronização e recuperação verificadas no ZUR e com duas conexões simuladas; segundo real adiado.
- [x] Fase 5 — Motor conferido com evidências do ZUR e testes; lacunas anteriores às conversões preservadas.
- [x] Fase 6 — Dashboards, tickets de origem e comparação de IA disponíveis e verificados.
- [ ] Fase 7 — Documentação e validação do ZUR concluídas; falta validar o segundo projeto real.

Uma fase só deve ser marcada como concluída quando suas entregas e seu critério de conclusão forem verificados. A conclusão de uma etapa não significa que a primeira versão inteira está pronta.

A primeira entrega técnica é a prova de viabilidade do histórico. A primeira entrega utilizável para análise ocorre ao concluir a fase 6; a liberação da primeira versão depende da validação da fase 7.

Prazos e estimativas de esforço devem ser definidos após a fase 1, com base no acesso e nas limitações reais do histórico. As fases não autorizam itens que estejam fora do escopo aprovado.

## Critérios de aceitação

- [ ] Os dois projetos podem ser configurados e sincronizados separadamente.
- [x] Nenhuma operação da integração altera dados no Jira.
- [x] A sincronização só é iniciada por solicitação do usuário.
- [x] Uma nova sincronização não duplica tickets ou eventos já armazenados.
- [x] Histórias e épicos não entram nas contagens.
- [x] Tarefas e subtarefas têm o mesmo peso, sem deduplicação entre mãe e filhas.
- [x] Trabalho não resolvido permanece visível nas sprints às quais pertenceu, conforme as regras de trabalho.
- [x] A conclusão de um ticket preserva os resultados históricos.
- [x] Reaberturas não aumentam a quantidade de primeiras entregas.
- [x] Bugs sem associação à sprint entram quando estiveram abertos no intervalo dela.
- [x] Bugs novos e existentes somam o total de bugs da sprint.
- [x] A proporção não é calculada quando o denominador é zero.
- [x] Os tickets de origem podem ser consultados para conferir cada indicador.
- [x] Sprints de transição e lacunas de histórico são identificadas.

Os critérios marcados foram verificados no ZUR e/ou em cenários automatizados e de navegador, conforme as evidências acima. O isolamento de duas conexões passou com Jira simulado; a aceitação real da segunda conexão permanece pendente e não foi marcada como concluída.

## Fora da primeira versão

- Filtro livre por datas.
- Pesos por story points, horas ou outras estimativas.
- Múltiplos quadros por projeto.
- Sincronização automática ou agendada.
- Hospedagem, acesso pela rede e uso compartilhado.
- Jira Server ou Data Center.
- Alterações de tickets pelo hub.
- Vínculo obrigatório entre bugs e entregas.
- Rankings entre projetos ou avaliação de produtividade individual.

## Próxima etapa

A aplicação pode ser usada localmente com o ZUR: abrir o dashboard, solicitar sincronização, selecionar sprints e conferir os tickets. A pendência para a liberação integral é a validação de ponta a ponta do segundo projeto real, quando estiver disponível. Manter as lacunas do histórico visíveis e respeitar o escopo aprovado; não iniciar recursos fora da primeira versão.

## Limpeza dos testes de validação (24/11/2026)

Por solicitação do usuário, foram removidos os testes exclusivos das ferramentas
de prova e conferência da fase 1. As quantidades citadas nas fases anteriores
permanecem como registro histórico das verificações realizadas na época.

- [x] Remover 48 testes das ferramentas auxiliares de validação.
- [x] Preservar as verificações do cliente Jira e das funções compartilhadas em `test_jira_client.py` e `test_jira_history.py`.
- [x] Verificar a suíte restante: 71 testes aprovados, sem credenciais reais ou consultas ao Jira.

Código funcional e validações de negócio preservados; a pendência da fase 7 continua aberta.

## Remoção dos arquivos de ambiente (24/11/2026)

- [x] Remover `.env` e `.env.example`, conforme solicitado pelo usuário.
- [x] Atualizar o README para o cadastro pela interface e a execução opcional das provas sem esses arquivos.
- [x] Conferir a ausência dos dois arquivos e preservar as regras que ignoram arquivos de ambiente no Git.

Banco, chave de criptografia e credenciais cadastradas permanecem preservados.
As referências anteriores ao `.env` nesta documentação são registros históricos.
