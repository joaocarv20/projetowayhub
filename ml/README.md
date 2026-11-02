# OptiRoute AI · Modelo de prazo de trânsito

Modelo supervisionado (regressão) que prevê em quantos dias um pacote chega ao destino depois da postagem.
É treinado com a base pública da Olist e servido pela API do WayHub (`POST /api/predict/transit`).

## Como rodar

1. Baixe o "Brazilian E-Commerce Public Dataset by Olist" no Kaggle e extraia os CSVs em `ml/data/`.
2. Instale as dependências e treine:

```bash
pip install -r ../backend/requirements.txt
python train.py
```

O treino leva alguns minutos e gera:

| Arquivo | Conteúdo |
|---|---|
| `models/transit_model.joblib` | modelo escolhido + modelo de prazo seguro (P90) + tabela de CEPs |
| `reports/relatorio.md` | relatório da entrega: dados, divisão, modelos, métricas, comparação com as linhas de base e análise de erros |
| `reports/metrics.json` | todos os números do relatório |
| `reports/figs/*.png` | gráficos para os slides |

## Arquivos

- `features.py`: monta as variáveis. É compartilhado entre o treino e a API, para que as entradas sejam montadas do mesmo jeito.
- `train.py`: carrega e limpa os dados, faz a divisão temporal (treino, validação e teste), calcula as linhas de base B0–B3,
  ajusta Random Forest e Gradient Boosting, faz a análise de erros e gera o relatório.
