# WayHub — Arquitetura do MVP

## Visão geral

```
┌──────────────────────────┐        HTTPS + JWT        ┌──────────────────────────────┐
│ SPA (frontend/)          │ ───────────────────────▶ │ API Flask (backend/app.py)   │
│ • Motorista (mobile)     │                           │ • security.py  JWT / storage │
│ • Centro (painel web)    │ ◀─────────────────────── │ • rules.py     regras        │
└──────────────────────────┘          JSON             │ • db.py        SQLite        │
                                                       └───────┬──────────────┬───────┘
                                                               │              │
                                                     wayhub.db (relacional)   private_storage/
                                                                              (CNH/CRLV → URLs assinadas)
```

| Camada | MVP | Produção sugerida |
|---|---|---|
| Banco | SQLite (`backend/schema.sql`) | PostgreSQL (mesmo schema, `SERIAL`/`TIMESTAMPTZ`) |
| Arquivos | Disco privado + URL assinada (itsdangerous, 5 min) | AWS S3 `generate_presigned_url` / Firebase Storage |
| Auth | JWT HS256, 8 h | JWT + refresh token / OAuth2 |
| Pagamento | `trip_orders.paid_at` registrado na validação do Código 2 | Gateway (Pix/Stripe/Pagar.me) via webhook |
| Tempo de percurso | Haversine × 1,3 ÷ 70 km/h (tabela de cidades) | Google Distance Matrix / OSRM |
| Prazo de entrega (ML) | Gradient Boosting treinado com a base Olist (`ml/`), carregado via joblib | Re-treino periódico com o histórico das próprias caronas |

## Modelo de dados

```
users 1─1 logistics_hubs 1─N orders (origin_hub_id / dest_hub_id)
users 1─1 drivers 1─1 vehicles
              drivers 1─N driver_documents (cnh | crlv | owner_id)
              drivers 1─N trips 1─N trip_orders N─1 orders
```

| Entidade | Campos principais |
|---|---|
| `users` | email (único), password_hash, role (`hub`/`driver`) |
| `logistics_hubs` | name, cnpj (único, validado), phone, cep, street, neighborhood, city, state |
| `drivers` | first_name, last_name, phone, origin_city, home_address, status (`pending_docs`/`active`/`blocked`) |
| `vehicles` | plate, model, color, year, cargo_type, capacity_kg, owned_by_third_party |
| `driver_documents` | doc_type, storage_key (privada), mime_type |
| `orders` | code (único), origin/dest hub, altura/largura/comprimento, peso, fee_cents, pickup_at, status |
| `trips` | driver_id, total_fee_cents, pickup_code (Código 1), delivery_code (Código 2), status |
| `trip_orders` | trip_id, order_id (único: um pedido só entra em uma viagem), fee_cents congelada, picked_up_at, delivered_at, paid_at |

Ciclo de status do pedido: `available → requested (Solicitado) → in_progress (Em Andamento) → closed (Encerrado)`; `cancelled` apenas a partir de `available`.

## Regras de negócio (`backend/rules.py`)

- **Taxa**: `R$ 0,50 + R$ 1,20 × kg taxável`, onde kg taxável = max(peso real, peso cubado a 300 kg/m³).
  Itens ultra-pequenos (≤ 1.000 cm³ e ≤ 0,3 kg) têm teto de **R$ 0,70** (ex.: capinha 15×8×2 cm → R$ 0,59).
- **Taxa mínima da viagem**: a soma das taxas selecionadas precisa ser ≥ **R$ 5,00** (validado no backend e na barra de checkout).
- **Multi-pedidos**: vários pedidos por viagem, limitados à `capacity_kg` do veículo.
- **Lock-in de 40 min**: o pedido só pode ser solicitado até 40 min antes de `pickup_at`. A busca esconde os pedidos fora do prazo,
  cada card mostra o cronômetro "Solicite em até…" e o checkout revalida no servidor. O Centro também não pode agendar retirada com menos de 40 min.
- **Concorrência**: a reserva usa `BEGIN IMMEDIATE`, então dois motoristas não conseguem reservar o mesmo pedido.
- **Handshake OTP**: os códigos 1 e 2 (6 dígitos, `secrets`) são gerados quando a viagem é criada, sem colisão com viagens abertas.
  - Código 1 é exibido ao motorista assim que a solicitação é aceita. O Centro de **origem** valida, e os pedidos daquele centro passam a `in_progress`.
  - Código 2 só é revelado depois da coleta. O Centro de **destino** valida, os pedidos passam a `closed` e o `paid_at` é registrado (pagamento automático).
  - Um código só vale no centro correto e no status correto. Se a viagem tiver pedidos de vários centros, cada centro libera/recebe apenas os seus.
- **Documentos**: CNH e CRLV são obrigatórios. Se "veículo em nome de outra pessoa" estiver marcado, o RG/CPF do proprietário também é obrigatório.
  No MVP, o motorista é aprovado automaticamente depois do envio completo (em produção entraria uma fila de análise).

## API REST

| Método | Rota | Perfil | Descrição |
|---|---|---|---|
| POST | `/api/auth/register/hub` | — | Cadastro de Centro Logístico |
| POST | `/api/auth/register/driver` | — | Cadastro de Motorista (passo 1) |
| POST | `/api/auth/login` | — | Login (`role` opcional confere o perfil) |
| GET | `/api/me` | ambos | Perfil + veículo |
| GET | `/api/hubs`, `/api/cities` | ambos / — | Centros para destino; cidades para busca |
| GET | `/api/pricing/quote` | — | Simulação de taxa |
| POST | `/api/predict/transit` | — | Previsão de prazo (OptiRoute AI): CEPs, peso e dimensões → dias esperados, prazo seguro P90 e média da rota |
| POST | `/api/driver/onboarding` | motorista | Veículo + uploads (multipart) |
| GET | `/api/driver/documents` | motorista | Documentos com URL assinada |
| GET | `/api/files/<token>` | — | Download via URL assinada (expira em 5 min) |
| GET | `/api/driver/orders/search` | motorista | `origin`, `destination`, `from`, `to` |
| POST | `/api/driver/trips` | motorista | `{order_ids: []}` → cria a viagem e devolve o Código 1 |
| GET | `/api/driver/trips` | motorista | Viagens, códigos e status |
| POST/GET | `/api/hub/orders` | centro | Cria / lista pedidos |
| POST | `/api/hub/orders/<id>/cancel` | centro | Cancela um pedido ainda disponível |
| GET | `/api/hub/monitoring` | centro | Tabela de monitoramento (saída e chegada) |
| POST | `/api/hub/validate-code` | centro | Valida o Código 1 ou o Código 2 (detecção automática) |

## Fluxos de tela

**Motorista (mobile-first, estilo BlaBlaCar)**
1. Login → perfil *Motorista* → Cadastro (dados pessoais) → **Veículo e documentos** (placa, modelo, cor, ano, tipo, CNH, CRLV, checkbox de terceiro → RG/CPF).
2. **Buscar**: Origem ⇅ Destino, data e horário → cards com cidades em destaque, centro/bairro, tamanho, dimensões, peso, tempo estimado, cronômetro e **Taxa de Carona**.
3. "+ Solicitar" adiciona o pedido à barra de checkout, que mostra o total, uma barra de progresso até R$ 5,00 e o peso em relação à capacidade. **Confirmar carona** fica habilitado quando o mínimo é atingido.
4. Modal com o **Código 1**. Em **Viagens**: Código 1 → (coleta) → Código 2 → encerrada/paga.

**Centro Logístico (painel web responsivo)**
1. Login → perfil *Centro Logístico* → Cadastro (com autopreenchimento de CEP via ViaCEP).
2. **Pedidos**: formulário (código opcional, destino, dimensões, peso, retirada) com cálculo da taxa em tempo real, e lista de pedidos com status e cancelamento.
3. **Acompanhamento**: caixa "Validar código", contadores por status e tabela (código, origem, destino, tempo médio, motorista com link de WhatsApp, status, pagamento), com filtros Saída/Chegada e atualização a cada 15 s.
