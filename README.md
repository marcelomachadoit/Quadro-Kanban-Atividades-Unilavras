# UniKanban — Gerenciador de Atividades Unilavras

Aplicativo desktop para Windows que entra no portal do aluno Unilavras, abre a **Sala de Aula Virtual**, verifica as **disciplinas com menos de 95% de conclusão**, coleta as atividades e avaliações **com prazo vigente ou pontuação** e organiza tudo em um **quadro Kanban** editável e salvo no seu computador.

> A automação é **somente leitura**: ela nunca envia respostas, nunca faz entregas e nunca altera nada no portal.

---

## 1. Requisitos

- Windows 10 ou 11
- **Google Chrome** instalado (o aplicativo usa o Chrome do computador)
- Para rodar pelo código-fonte: **Python 3.12 ou superior** (testado com 3.14.7)

## 2. Usar o executável (sem instalar Python)

1. Copie a pasta `dist\UniKanban\` para onde quiser (ex.: `C:\Programas\UniKanban`).
2. Dê dois cliques em **`UniKanban.exe`**.
3. (Opcional) Verifique se o Chrome e a automação estão funcionando:
   `UniKanban.exe --diagnostico` (código de saída 0 = tudo certo).

## 3. Instalar e executar pelo código-fonte

No PowerShell, dentro da pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Não é preciso rodar `playwright install`: o aplicativo usa o Google Chrome já instalado.

## 4. Configurar as credenciais

1. Abra o aplicativo e clique em **Configurações**.
2. Preencha **Usuário** e **Senha** do portal do aluno. O botão **Mostrar senha** exibe ou oculta o que você digitou.
3. Clique em **Salvar credenciais**.
4. Clique em **Testar conexão** para confirmar o login. A data da **última autenticação bem-sucedida** aparece logo abaixo.

Para trocar o usuário ou a senha, edite os campos e salve de novo. **Remover credenciais** apaga os dados do cofre.

**Segurança:** a senha fica no **Gerenciador de Credenciais do Windows** (Painel de Controle › Gerenciador de Credenciais › Credenciais do Windows › `UniKanban/novoportal.unilavras.edu.br`). Ela nunca é gravada no banco de dados, em arquivos de configuração ou nos registros (logs). Os logs passam por um filtro que remove senhas, tokens e cookies.

### Autenticação manual (CAPTCHA, verificação em duas etapas, Microsoft 365)

Por padrão, a janela do Chrome fica **visível** durante a atualização (opção em Configurações › Navegador). Se o portal pedir CAPTCHA, verificação em duas etapas ou login Microsoft 365, o aplicativo mostra o aviso *"Conclua a autenticação na janela do Chrome"*. Conclua a etapa no navegador e a automação continua sozinha. O tempo limite é de 5 minutos.

O aplicativo nunca tenta contornar esses mecanismos. Se a opção "navegador oculto" estiver ativa e o portal pedir verificação, você verá uma mensagem pedindo para reativar a janela visível.

### "Verificação de segurança" após várias tentativas (Cloudflare Turnstile)

O login do portal é protegido pelo Cloudflare Turnstile, que fica invisível na maior parte do tempo. Depois de **várias tentativas de login seguidas**, o portal passa a exigir uma verificação humana e mostra *"Conclua a verificação de segurança antes de continuar"*. No Chrome controlado pela automação essa verificação **não pode ser concluída** (o portal exibe *"Não foi possível concluir a verificação neste navegador"*).

Nesse caso, o UniKanban **não** diz que a senha está errada. Ele explica o que aconteceu e o que fazer:

1. Em Configurações, clique em **Abrir portal no navegador** (abre o seu navegador habitual).
2. Entre normalmente no portal e conclua a verificação.
3. Aguarde alguns minutos e clique em **Atualizar dados** de novo, sem repetir tentativas em sequência.

O portal guarda a sessão em `sessionStorage`, que é apagado quando o navegador fecha. Por isso cada atualização faz um novo login: a sessão não pode ser reaproveitada entre execuções.

## 5. Como usar

**Primeiro uso:** a tela inicial pede seu usuário e senha do portal. Clique em **Conectar e buscar atividades**: o aplicativo salva a conta com segurança e já monta o quadro.

| Tela | O que faz |
|---|---|
| **Início** | Saudação e resumo em uma frase ("2 entregas vencem nas próximas 48 horas"). Quatro indicadores clicáveis (*Vencem em até 48 h*, *A fazer*, *Em andamento*, *Concluídas*) abrem o quadro já filtrado. **Próximas entregas** agrupadas em *Atrasadas, Hoje, Amanhã, Esta semana, Mais adiante, Sem prazo*, com o ○ para concluir em um clique |
| **Quadro** | Colunas *A fazer*, *Em andamento* e *Concluído*. Cada cartão mostra a cor e o nome curto da disciplina (sem o código), o prazo em linguagem natural ("Amanhã, 23:30 · faltam 31 h") e os pontos. **Clique no cartão** para abrir o painel lateral, **arraste** para mover ou reordenar, **○** conclui e o botão direito abre o menu (abrir no portal, mover, excluir) |
| **Painel da atividade** | Abre ao lado do quadro: edite nome, status, disciplina, prazo, pontuação e observações, resolva divergências com o portal ("Manter o meu" / "Usar do portal"), abra no portal ou exclua. Avisa antes de descartar alterações não salvas |
| **Filtros** | Busca por nome ou disciplina, chips coloridos por disciplina, **Só urgentes**, **Ocultar concluídas**, ordenação (prazo, ordem manual, nome), alternância **quadro/lista** e **Excluídas** (para restaurar) |
| **Atualizar agora** | Fica sempre visível na barra lateral. Roda em segundo plano, com uma barra discreta "Carregando dados do portal…" (etapa, disciplina, progresso e **Interromper**). Ao terminar, uma notificação resume o que mudou e leva ao resumo completo. Erros aparecem em uma faixa com a ação certa (ex.: **Abrir portal no navegador**, **Revisar conta**) |
| **Configurações** | Conta do portal (status da conexão, salvar, testar, abrir portal), opção de mostrar o Chrome, exportar para Excel/CSV, backup/restauração e, recolhido em **Avançado**, os nomes das opções do portal e as pastas de dados e logs |

Ações rápidas, como concluir, mover ou excluir, mostram uma notificação com **Desfazer**.

**Atalhos:** `F5` atualizar · `Ctrl+N` nova atividade · `Ctrl+F` buscar · `Esc` fechar o painel · `Ctrl+1/2/3` Início, Quadro, Configurações.

Os indicadores de prazo combinam cor, ícone e texto, para não depender só da cor: *Prazo encerrado*, *Vence em breve* (até 48 h, com as horas restantes), *Esta semana*, *No prazo*, *Sem prazo* e *Concluída*. Os cartões também sinalizam ⚠ *divergência com o portal* e ? *não encontrada na última verificação*.

## 6. Regras implementadas

- **Disciplinas:** processa somente as com conclusão **< 95%** (94% entra; 95% e 100% ficam de fora). Se o percentual estiver ausente ou não puder ser lido, a disciplina **não** é processada e aparece no relatório.
- **Atividades:** entram itens avaliativos com **prazo vigente** e/ou **pontuação**. Itens com prazo expirado ficam de fora. Avaliações sem prazo, mas com pontuação, entram com prazo "-". Materiais (vídeos, slides, leituras) são ignorados, a menos que tenham pontuação.
- **Datas:** fuso `America/Sao_Paulo`. Uma data sem horário vale até 23:59:59 daquele dia. Datas ambíguas ou ilegíveis **não são descartadas**: entram marcadas como "Verificar data" e aparecem no relatório.
- **Pontuação:** registra o valor **total** da atividade ("Vale 4 pontos"), e não a nota obtida.
- **Campos ausentes** recebem "-". Nada é inventado.
- **Atualização incremental:** cada atividade tem um identificador único (o ID do item no portal, `grupoa:<id>`), com reserva por disciplina e nome normalizados. A atualização insere o que é novo, atualiza o que mudou e informa as contagens de encontradas, adicionadas, atualizadas e sem alterações.
- **Seu trabalho é preservado:** status, observações, posição e edições manuais nunca são sobrescritos. Os valores do portal e os seus ficam em colunas separadas. Se o portal mudar um campo que você editou, sua edição é mantida e o cartão mostra **⚠ Divergência**; em *Detalhes* você escolhe "Usar valor do portal" ou "Manter o meu valor".
- **Atividades que somem do portal** não são apagadas: ficam marcadas como *Não encontrada na última verificação*. Só são marcadas assim se a disciplina foi lida com sucesso.
- **Prazo alterado no portal:** a data é atualizada e a mudança aparece no resumo.
- **Exclusão local:** pede confirmação e tira a atividade do quadro (ela fica em *Excluídas*, de onde pode ser restaurada). Na próxima atualização, as atividades que ainda existirem no portal **voltam ao quadro**, sem duplicar e com status e observações preservados. Atividades criadas manualmente continuam excluídas.

## 7. Onde ficam os dados

`%LOCALAPPDATA%\UniKanban\`

- `unikanban.db`: banco SQLite (modo WAL, resistente a fechamentos inesperados), criado automaticamente na primeira execução
- `logs\unikanban.log`: registros rotativos, sem dados sensíveis
- `chrome-profile\`: perfil do Chrome usado pela automação (mantém o login entre atualizações)
- `diagnostico\`: capturas de tela salvas quando uma disciplina falha

Os backups (**Configurações › Fazer backup**) são cópias consistentes do banco. Ao restaurar, o aplicativo valida o arquivo e guarda uma cópia dos dados atuais antes de substituí-los.

## 8. Gerar o executável

```powershell
.\.venv\Scripts\pyinstaller.exe UniKanban.spec --noconfirm
```

O resultado fica em `dist\UniKanban\UniKanban.exe` (cerca de 270 MB, distribuído como pasta). Para recriar o ícone: `.\.venv\Scripts\python.exe assets\make_icon.py`.

## 9. Testes

```powershell
# Testes unitários e de interface (dados simulados; não acessam o portal)
.\.venv\Scripts\python.exe -m pytest -q

# Integração com o portal real (opcional; credenciais só em variáveis de ambiente da sessão)
$env:UNIKANBAN_TEST_USER = "seu_usuario"
$env:UNIKANBAN_TEST_PASSWORD = "sua_senha"
.\.venv\Scripts\python.exe -m pytest tests\test_integration_portal.py -v -s
Remove-Item Env:UNIKANBAN_TEST_USER, Env:UNIKANBAN_TEST_PASSWORD
```

| Arquivo | Cobre (itens da especificação) |
|---|---|
| `tests/test_rules.py` | 1, 2 seleção ≥/< 95% · 3, 4 prazos futuros e expirados · 5 sem prazo com pontuação · 6 campos "-" · 7 datas no fuso de São Paulo · 8 chave de duplicatas · pontuação total × obtida |
| `tests/test_sync_db.py` | 8 duplicatas · 9 atualização incremental · 10 preservação de status e observações · 11 persistência após reinício · 12 divergências · 13 exportação CSV/Excel e backup |
| `tests/test_updater.py` | Fluxo completo com cliente simulado · 14 falhas de conexão, novas tentativas, sessão expirada, cancelamento, mudança de estrutura e login recusado |
| `tests/test_security_ui.py` | Cofre de credenciais, senha fora do banco, filtro de logs, Kanban (soltar cartão, busca, chips de disciplina, concluir com Desfazer), painel lateral (editar e criar), tela inicial e primeiro uso |
| `tests/test_ui_format.py` | Prazos em linguagem natural, níveis de urgência com texto, nomes curtos de disciplina, pontos, agrupamento e tempo relativo |
| `tests/test_login_detection.py` | Resultado do login com páginas simuladas: senha errada × verificação de segurança × verificação pendente |
| `tests/test_integration_portal.py` | Portal real: atualização completa, segunda execução sem duplicatas e teste de conexão. O teste de senha errada só roda com `UNIKANBAN_TEST_WRONG_PASSWORD=1`, porque tentativas falhas levam o portal a exigir verificação humana |

## 10. Arquitetura

```
main.py                     inicialização, tema, tratamento global de erros, --diagnostico
app/config.py               caminhos, fuso, limites (tempos, tentativas) e regras (95%, 48 h)
app/models/activity.py      Course, ScrapedActivity, Activity (valores do portal × do usuário)
app/database/db.py          SQLite: esquema versionado, WAL, transações, lixeira, histórico
app/services/rules.py       regras puras: percentuais, datas BR/ISO, pontuação, inclusão, chaves
app/services/sync.py        mesclagem incremental, divergências, edições do usuário
app/services/updater.py     orquestra login → sala virtual → disciplinas → atividades → banco
app/services/credentials.py Gerenciador de Credenciais do Windows (keyring)
app/services/logging_setup.py logs rotativos com remoção de segredos
app/automation/portal.py    Playwright + Chrome: login, pausa manual, navegação, novas tentativas
app/automation/parser.py    interpretação dos dados da Plataforma A (testável sem navegador)
app/export/exporter.py      CSV, Excel, backup e restauração
app/ui/                     PySide6: início, quadro (Kanban/lista), painel lateral, notificações, tema e
                            ícones nativos, configurações, workers; format.py = textos em linguagem natural
tests/                      pytest
```

**Como o portal foi mapeado (inspeção real, out/2026):**

1. `novoportal.unilavras.edu.br/sessions/login` (Angular): campos `#username`/`#password`, botão **Acessar**, redireciona para `/portal`.
2. O bloco **Sala de Aula Virtual** abre em nova aba a **Plataforma A (Grupo A)**, em `unilavrasedu.grupoa.education/plataforma`, com um token de uso único.
3. O menu **Disciplinas** (`/plataforma/my-enrollments/courses`) lista as disciplinas com "NN% concluído". A página carrega esses dados de `api.plataforma.grupoa.education/.../academic/courses/me` (campos `id`, `name`, `progress`, `nextPage`).
4. Cada disciplina (`/plataforma/course/{id}`) carrega uma árvore de tópicos (ciclos, seções e itens) em `.../content/academics-main/{id}/contents`. Os itens avaliativos têm `hasDeadline`/`deadlineAt` (exibido como "Prazo de envio 30/10/2026 - 23:59") e `hasGrade`/`grade.value` (exibido como "Vale 4 pontos").
5. Página da atividade: `/plataforma/course/{id}/content/{itemId}`.

A automação navega pela interface real, como um aluno faria, e lê os dados que as próprias páginas carregam, interceptados de forma passiva com `expect_response`. Os elementos são localizados por texto e papel acessível ("Sala de Aula Virtual", "Disciplinas", "Acessar"), e não por posição. Se os dados da lista de disciplinas não vierem, há uma leitura alternativa pela tela ("NN% concluído"). A interface roda em `QThread`, então não congela. Cada disciplina é gravada no banco assim que termina, e uma interrupção não perde o que já foi coletado.

## 11. Limitações conhecidas

- **Seções bloqueadas por condições** (ex.: "Ciclo IV", "Prova I: 12/11", liberadas só depois de concluir etapas anteriores) não mostram seus itens até serem liberadas. O aplicativo inspeciona tudo o que está acessível. Quando o título de uma seção bloqueada indica uma avaliação com data (ex.: "Prova I: 12/11"), ela entra no quadro com essa data (o ano vem do início da disciplina) e pontuação "-".
- Unidades de conteúdo da editora (ex.: "Desafio" e "Exercícios" dentro de uma unidade SAGAH) não informam prazo nem pontuação no portal e, por isso, não entram.
- Paginação da lista de disciplinas: o caso com mais de 20 disciplinas (`nextPage`) está implementado, mas não pôde ser testado na conta real, que tem 6 disciplinas.
- O login via **Microsoft 365** e as verificações humanas foram implementados como pausa para ação manual, mas não puderam ser testados porque a conta de teste entra com usuário e senha sem verificação adicional.
- Se o Grupo A mudar o formato dos dados, a atualização informa que *"a estrutura do portal pode ter mudado"* e os dados locais ficam preservados. Os nomes "Sala de Aula Virtual" e "Disciplinas" podem ser ajustados em Configurações › Avançado.
- A atualização completa pelo **executável** foi validada com `--diagnostico` (Chrome + Playwright abrindo o portal) e com a abertura da interface. O fluxo completo com login foi validado pelo código-fonte, que é o mesmo código empacotado.
