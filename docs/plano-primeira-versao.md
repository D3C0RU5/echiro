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

Todas as fases abaixo estão planejadas, ainda não executadas. A sequência mantém o escopo aprovado e aproveita a base existente: API em Python/FastAPI e frontend em React/TypeScript/Vite.

| Fase | Resultado principal | Depende de |
| --- | --- | --- |
| 1. Viabilidade do histórico | Evidências de que os dados sustentam as métricas | Acesso de leitura aos dois projetos |
| 2. Base local e persistência | Aplicação preparada para armazenar dados e proteger credenciais | Fase 1 |
| 3. Cadastro e configuração | Dois projetos configuráveis com suas próprias regras | Fase 2 |
| 4. Sincronização manual | Histórico coletado, atualizado e rastreável | Fase 3 |
| 5. Motor de métricas | Indicadores calculados e conferíveis por sprint | Fase 4 |
| 6. Dashboards e análise de IA | Fluxo completo de consulta e comparação | Fase 5 |
| 7. Validação da primeira versão | Uso local validado com os dois projetos reais | Fase 6 |

### Fase 1 — Validar a viabilidade do histórico do Jira

**Objetivo:** confirmar a disponibilidade dos dados antes de construir indicadores que dependem deles.

Entregas:

- [ ] Fazer uma prova de integração somente de leitura, usando acesso fornecido para os dois projetos e sem versionar segredos.
- [ ] Verificar obtenção de projetos, quadro, colunas, status, tipos de tickets, sprints e histórico dos tickets.
- [ ] Validar recuperação paginada de todo o histórico necessário, incluindo mudanças de status e de participação em sprints.
- [ ] Conferir exemplos de tarefas carregadas entre sprints, tickets removidos, subtarefas, primeiras conclusões e bugs reabertos.
- [ ] Verificar como identificar participação de subtarefas quando a associação à sprint não estiver explícita; documentar a evidência e não presumir herança da tarefa mãe.
- [ ] Definir e registrar o uso de datas de início/fim das sprints, o tratamento da sprint em andamento, o fuso horário e os limites dos intervalos.
- [ ] Registrar limitações de permissões e de histórico, além da correspondência entre colunas e status. Identificar mudanças históricas de configuração que não possam ser reconstruídas.

**Critério de conclusão:** conseguir explicar, com exemplos conferidos, como reconstruir cada indicador nos dois projetos. Uma limitação que impeça uma regra aprovada deve ser resolvida ou apresentada para decisão antes de implementar essa regra; nunca substituída silenciosamente por uma aproximação.

### Fase 2 — Preparar a base local e a persistência

**Objetivo:** estabelecer armazenamento e organização técnica para suportar cadastro, coleta e cálculo.

Entregas:

- [ ] Separar na API as responsabilidades de integração com Jira, persistência, sincronização e métricas.
- [ ] Definir o banco local e a estratégia de evolução do esquema. SQLite é a opção inicial proposta, a confirmar nesta fase.
- [ ] Modelar projetos, conexões, regras de classificação, quadro, sprints, tickets, eventos históricos e execuções de sincronização.
- [ ] Usar identificadores do Jira associados ao projeto/conexão para impedir mistura de dados entre projetos.
- [ ] Definir armazenamento protegido de credenciais, mantendo material de proteção separado dos dados protegidos; excluir segredos e dados locais do controle de versão.
- [ ] Garantir que credenciais não sejam devolvidas ao frontend após o cadastro nem registradas em logs.
- [ ] Preparar execução restrita à máquina local, incluindo configuração de portas do ambiente de desenvolvimento.
- [ ] Preparar a estrutura de testes das regras de domínio e da integração, sem depender de credenciais reais na execução automatizada.

**Critério de conclusão:** dados de projetos persistem após reiniciar a aplicação, permanecem isolados e podem ser recuperados pela API; o mecanismo de proteção das credenciais e a execução local estão definidos e verificados.

### Fase 3 — Implementar cadastro e configuração dos projetos

**Objetivo:** permitir preparar os dois projetos pela interface, sem editar código.

Entregas:

- [ ] Criar listagem, cadastro e edição dos projetos, cada um com sua URL e credenciais.
- [ ] Implementar teste de conexão e mensagens compreensíveis para falhas de autenticação, permissão ou comunicação.
- [ ] Buscar metadados do Jira por ação do usuário para escolher um quadro, tipos de tickets, colunas de trabalho e status finais.
- [ ] Permitir múltiplas seleções e regras finais próprias para tarefas e bugs.
- [ ] Registrar a data de adoção de IA.
- [ ] Validar configurações incompletas ou conflitantes, como um tipo classificado simultaneamente como tarefa e bug.
- [ ] Definir que alterações nas regras exigem recálculo dos indicadores e identificar resultados ainda calculados com configuração anterior.

**Critério de conclusão:** cadastrar e configurar os dois projetos com credenciais independentes; as escolhas persistem e nenhum projeto consulta ou altera a configuração do outro.

### Fase 4 — Implementar a sincronização manual do histórico

**Objetivo:** construir uma base local completa e atualizável, com execução explícita pelo usuário.

Entregas:

- [ ] Implementar a coleta inicial de todo o histórico disponível do projeto, incluindo bugs que não pertencem ao quadro ou às sprints selecionadas.
- [ ] Coletar tickets, sprints e eventos necessários para reconstrução temporal, percorrendo todas as páginas de resultados.
- [ ] Implementar atualizações incrementais e tratamento de falhas, com tentativas controladas e respeito aos limites de requisição encontrados na integração.
- [ ] Usar gravações idempotentes e pontos de retomada para evitar duplicidade ou perda de dados em nova execução.
- [ ] Impedir execuções concorrentes conflitantes para o mesmo projeto.
- [ ] Exibir estados de execução, progresso disponível, última sincronização bem-sucedida e erros por projeto.
- [ ] Preservar a última base consistente em caso de falha e sinalizar atualização incompleta, sem apresentá-la como coleta concluída.
- [ ] Registrar lacunas e alterações de metadados que afetem a configuração ou o cálculo.

**Critério de conclusão:** a coleta inicial funciona nos dois projetos; repetir a sincronização não duplica registros; uma execução interrompida pode ser retomada ou refeita sem corromper os dados; não há início automático ou agendamento.

### Fase 5 — Implementar o motor de métricas por sprint

**Objetivo:** transformar o histórico em indicadores reproduzíveis, conforme as regras aprovadas.

Entregas:

- [ ] Reconstruir os intervalos de participação em sprints e os estados de trabalho e conclusão de cada ticket.
- [ ] Calcular tarefas e subtarefas trabalhadas, preservando trabalho iniciado antes e ainda não resolvido durante sua participação na sprint.
- [ ] Contar cada ticket uma vez por sprint e cada primeira conclusão uma vez no histórico, separando reaberturas.
- [ ] Calcular bugs que estiveram abertos em qualquer parte do intervalo, inclusive sem associação à sprint.
- [ ] Separar bugs novos e existentes e calcular a proporção principal.
- [ ] Retornar junto dos indicadores os tickets que sustentam cada contagem e eventuais limitações de completude.
- [ ] Recalcular resultados após sincronizações e mudanças nas regras, preservando os eventos de origem.
- [ ] Implementar testes de domínio para tarefas mães e subtarefas, mudanças de sprint, trabalho persistente, reaberturas, bugs criados e resolvidos no mesmo intervalo, limites de datas e denominador zero.

**Critério de conclusão:** os cálculos correspondem aos exemplos conferidos nos dois projetos; novos mais existentes equivalem aos bugs totais; nenhuma reabertura duplica uma primeira entrega; lacunas não são representadas como zero.

### Fase 6 — Construir dashboards e comparação da adoção de IA

**Objetivo:** disponibilizar a análise por projeto com navegação até os tickets de origem.

Entregas:

- [ ] Criar navegação entre os projetos e seleção de sprints.
- [ ] Exibir totais de trabalhadas, entregues, reaberturas e bugs, além da proporção e da separação entre bugs novos e existentes.
- [ ] Mostrar gráficos de evolução por sprint e tabelas de tickets acessíveis a partir dos indicadores.
- [ ] Marcar a adoção de IA e identificar sprints anteriores, posteriores e de transição.
- [ ] Apresentar totais e médias por sprint para os grupos anteriores e posteriores; manter sprints de transição identificadas separadamente e fora dessas médias.
- [ ] Mostrar a quantidade de sprints em cada grupo e distinguir sprints em andamento das encerradas para evitar comparações apresentadas como equivalentes sem indicação.
- [ ] Tratar estados sem dados, ausência de períodos antes/depois, proporção não calculável, sincronização em curso e histórico incompleto.
- [ ] Manter visíveis a última sincronização e a configuração usada nos resultados.

**Critério de conclusão:** selecionar um projeto e suas sprints, entender os indicadores, abrir os tickets que explicam cada número e comparar os períodos de adoção sem misturar os projetos nem ocultar lacunas.

### Fase 7 — Validar e preparar o uso local da primeira versão

**Objetivo:** confirmar o funcionamento completo e documentar a operação cotidiana.

Entregas:

- [ ] Executar o fluxo completo nos dois projetos: cadastro, configuração, sincronização, dashboard e conferência dos tickets.
- [ ] Conferir amostras de sprints encerradas e em andamento, incluindo casos de reabertura e trabalho carregado entre sprints quando disponíveis.
- [ ] Validar reinício da aplicação, nova sincronização, mudança de regras e recuperação de falhas de rede ou credenciais.
- [ ] Conferir que a integração não realiza escritas no Jira e que segredos não aparecem em respostas, logs ou arquivos versionados.
- [ ] Rodar os testes das métricas, verificações da API e build do frontend.
- [ ] Documentar instalação, execução local, configuração das credenciais, sincronização, localização dos dados, cópia de segurança e limitações conhecidas.
- [ ] Conferir todos os critérios de aceitação deste plano.

**Critério de conclusão:** os dois projetos podem ser acompanhados localmente de ponta a ponta, os critérios de aceitação estão atendidos e as limitações encontradas estão documentadas.

### Acompanhamento das fases

Todas as caixas começam desmarcadas. Marcar cada entrega após a verificação e a fase inteira somente quando seu critério de conclusão também estiver atendido.

- [ ] Fase 1 — Viabilidade do histórico validada.
- [ ] Fase 2 — Base local e persistência verificadas.
- [ ] Fase 3 — Cadastro e configuração dos dois projetos disponíveis.
- [ ] Fase 4 — Sincronização manual e recuperação de falhas verificadas.
- [ ] Fase 5 — Motor de métricas conferido com exemplos e testes.
- [ ] Fase 6 — Dashboards e comparação de IA disponíveis.
- [ ] Fase 7 — Validação final e documentação de uso concluídas.

Uma fase só deve ser marcada como concluída quando suas entregas e seu critério de conclusão forem verificados. A conclusão de uma etapa não significa que a primeira versão inteira está pronta.

A primeira entrega técnica é a prova de viabilidade do histórico. A primeira entrega utilizável para análise ocorre ao concluir a fase 6; a liberação da primeira versão depende da validação da fase 7.

Prazos e estimativas de esforço devem ser definidos após a fase 1, com base no acesso e nas limitações reais do histórico. As fases não autorizam itens que estejam fora do escopo aprovado.

## Critérios de aceitação

- [ ] Os dois projetos podem ser configurados e sincronizados separadamente.
- [ ] Nenhuma operação da integração altera dados no Jira.
- [ ] A sincronização só é iniciada por solicitação do usuário.
- [ ] Uma nova sincronização não duplica tickets ou eventos já armazenados.
- [ ] Histórias e épicos não entram nas contagens.
- [ ] Tarefas e subtarefas têm o mesmo peso, sem deduplicação entre mãe e filhas.
- [ ] Trabalho não resolvido permanece visível nas sprints às quais pertenceu, conforme as regras de trabalho.
- [ ] A conclusão de um ticket preserva os resultados históricos.
- [ ] Reaberturas não aumentam a quantidade de primeiras entregas.
- [ ] Bugs sem associação à sprint entram quando estiveram abertos no intervalo dela.
- [ ] Bugs novos e existentes somam o total de bugs da sprint.
- [ ] A proporção não é calculada quando o denominador é zero.
- [ ] Os tickets de origem podem ser consultados para conferir cada indicador.
- [ ] Sprints de transição e lacunas de histórico são identificadas.

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

Iniciar pela fase 1, validando a recuperação do histórico necessário nos dois projetos. As decisões técnicas de persistência e proteção das credenciais serão consolidadas na fase 2, com base nas evidências da integração e no escopo aprovado.
