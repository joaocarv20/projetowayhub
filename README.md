# 🚚 WayHub
"BlaBlaCar de pedidos" entre centros logísticos. Python + Streamlit + MySQL (Workbench) + IA (scikit-learn).

## Como rodar
1. `pip install -r requirements.txt`
2. No **MySQL Workbench**, execute **nesta ordem** (⚡):
   1. `database/schema.sql` — cria o banco e as tabelas (*apaga o banco `wayhub` antigo e recria do zero*);
   2. `database/dados_treino_exemplo.sql` — 800 entregas fictícias para a IA treinar (tabela `historico_entregas`);
   3. `database/dados_ficticios.sql` — *(opcional, para demonstração)* 13 centros, 20 motoristas, 155 caronas e ~600 pedidos fictícios. Logins: `centro01@wayhub.test` … `motorista01@wayhub.test`, senha `123456`.
3. Abra o `.env` e coloque a senha do seu MySQL em `WAYHUB_DB_PASSWORD` (modelo em `.env.example`).
4. `streamlit run app.py` — na primeira abertura a IA é treinada (alguns segundos).

## Fluxo para testar
1. Cadastre **2 centros logísticos** (CNPJ válido, cidades diferentes) e **1 motorista** (entra direto, sem aprovação).
2. Centro A: cadastre pedidos (retirada daqui a 40+ min) para o centro B — o card mostra a previsão da IA.
3. Motorista: filtre, selecione pedidos (mín. R$ 5,00, mesma rota) e **solicite a carona** → aparece o código de retirada.
4. Centro A → *Acompanhamento*: digite o código de retirada → **Em andamento**. O motorista ganha o código de entrega.
5. Centro B → *Acompanhamento*: digite o código de entrega → **Encerrado** e taxa **paga**.

## Estrutura de pastas e função de cada arquivo
| Pasta / arquivo | Função |
|---|---|
| `app.py` | Entrada: conecta ao banco, treina a IA ao iniciar e abre a tela de cada perfil |
| `config/settings.py` | Configurações: banco (.env), prazos, taxa mínima, cidades e parâmetros da IA |
| `database/connection.py` | Conexão com o MySQL (`query`, `execute`, `transaction`) |
| `database/schema.sql` | Cria o banco e as tabelas no Workbench |
| `domain/usuarios.py` | POO: `Usuario` (abstrata) → `Motorista`, `CentroLogistico`; `Veiculo` |
| `domain/pedidos.py` | POO: `Pedido` e `CalculadoraTaxa` (valor pago ao motorista) |
| `services/logistica.py` | Regras: carona, códigos, status, pagamento, expiração, tempo médio, sugestões |
| `ml/geografia.py` | Coordenadas das cidades e distância estimada em km |
| `ml/preparacao_dados.py` | Lê `historico_entregas` + entregas encerradas do MySQL e monta as variáveis da IA |
| `ml/treinamento.py` | Treina o Random Forest e grava `data/metricas_modelo.json` |
| `ml/visao.py` | Visão computacional (OpenCV): mede o produto por fotos sobre uma folha A4 (de cima + deitado de lado para a altura) e estima o peso pela descrição |
| `ml/previsao.py` | `PrevisorEntrega`: prevê o tempo (em horas) de um ou vários pedidos |
| `ml/gerar_dados_exemplo.py` | Gera `dados_treino_exemplo.sql` e `entregas_historico.csv` (mesmos dados **fictícios**) |
| `database/dados_treino_exemplo.sql` | Insere 800 entregas fictícias em `historico_entregas` (troque pelas reais) |
| `database/gerar_dados_ficticios.py` | Gera o `dados_ficticios.sql` (centros, motoristas, caronas e pedidos fictícios) |
| `database/dados_ficticios.sql` | Popula o banco para demonstração (rode depois do schema) |
| `data/entregas_historico.csv` | Os **mesmos** 800 dados de treino em CSV (para Excel, Python ou importar no Workbench) |
| `ui/tema.py` | Visual estilo BlaBlaCar |
| `ui/login_view.py` · `centro_view.py` · `motorista_view.py` | Telas de login/cadastro, do centro e do motorista |
| `utils/helpers.py` | Validações, formatação (R$, telefone, dias) e senha criptografada |

## Base de treino da IA — tabela `historico_entregas` (no Workbench)
Cada linha é **uma entrega já realizada**. Colunas:

| Coluna | Exemplo | Observação |
|---|---|---|
| `cidade_origem` | `Anápolis - GO` | Igual ao nome da lista de cidades do sistema (`config/settings.py`) |
| `cidade_destino` | `Goiânia - GO` | idem |
| `distancia_km` | `60.5` | Pode ficar `NULL`: o sistema estima pela localização das cidades |
| `peso_kg` | `0.5` | |
| `altura_cm`, `comprimento_cm`, `largura_cm` | `10`, `20`, `15` | O volume é calculado sozinho |
| `retirado_em` | `2026-03-10 09:30:00` | |
| `entregue_em` | `2026-03-11 14:00:00` | |

**Como alimentar (Workbench):**
- Rode `database/dados_treino_exemplo.sql` para carregar 800 entregas **fictícias** (o CSV `data/entregas_historico.csv` tem os mesmos dados) (só para o protótipo funcionar).
- Para os dados reais, use `INSERT` ou clique com o direito na tabela → **Table Data Import Wizard** e importe um CSV com esses nomes de coluna.
- Para trocar tudo pelos reais: `DELETE FROM historico_entregas;` e importe de novo.

O sistema calcula sozinho o tempo em **horas** (`entregue_em − retirado_em`), o dia da semana e a hora da retirada.
A previsão é **sempre mostrada em dias** ("até 1 dia", "até 2 dias"...).

Como a IA aprende (**aprendizado contínuo / autossupervisionado**): cada entrega encerrada no WayHub vira, sozinha,
um novo exemplo de treino — o próprio sistema registra a retirada e a entrega, então o tempo real é o "gabarito".
Sempre que uma entrega é encerrada (ou a tabela `historico_entregas` muda), a IA se retreina automaticamente,
juntando `historico_entregas` com as entregas encerradas. Não existe botão de retreinar. Entregas do WayHub com menos de 30 min são consideradas testes e não treinam a IA.
O erro médio do último treino fica em `data/metricas_modelo.json`.

## Rodar no Windows 10/11 (notebook da apresentação)
1. **Copie a pasta inteira** por pendrive/zip (não por Git: o `.env` não vai pelo Git). Não precisa copiar `__pycache__`.
2. Instale o **Python 3.12** (python.org) marcando **"Add python.exe to PATH"**.
3. Instale o **MySQL Server 8.4 + MySQL Workbench** (MySQL Installer). Na senha do `root`, use **a mesma do `.env`** (ou troque o `.env`).
4. No Workbench do notebook, rode na ordem: `schema.sql` → `dados_treino_exemplo.sql` → `dados_ficticios.sql`.
5. Dê dois cliques em **`INSTALAR_WINDOWS.bat`** (uma vez, com internet).
6. Para abrir: **`INICIAR_WAYHUB.bat`** → abre `http://localhost:8501`. Se o Firewall perguntar, pode permitir.
