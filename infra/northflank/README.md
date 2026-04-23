# Northflank deploy

Configuração mínima para publicar o projeto no Northflank com menor custo operacional.

## Serviços

1. `backend`
   - Build from Git
   - Dockerfile: `Dockerfile.backend`
   - Porta pública: `8000`
   - Health check: `/api/v1/health/ready`
   - Volume persistente montado em `/data`

2. `frontend`
   - Build from Git
   - Dockerfile: `Dockerfile.frontend`
   - Porta pública: `3000`
   - Health check: `/`
   - Dependência lógica do backend via variáveis de ambiente

## Variáveis

- Backend: use `infra/northflank/backend.env.example`
- Frontend: use `infra/northflank/frontend.env.example`

## Ajustes recomendados

- Crie um volume persistente para o backend e monte em `/data`.
- Aponte `SNAPMAKER_STORAGE_ROOT=/data/SnapMaker3d`.
- Em produção, use `OLLAMA_ENABLED=false` até existir um endpoint LLM público confiável.
- Ajuste `PUBLIC_BACKEND_ORIGIN`, `ALLOWED_ORIGINS`, `NEXT_PUBLIC_API_BASE_URL` e `NEXT_PUBLIC_BACKEND_ORIGIN` para os domínios reais gerados pelo Northflank.

## Sequência de deploy

1. Criar projeto `snapmaker3d-studio`.
2. Criar serviço `backend` usando `Dockerfile.backend`.
3. Anexar volume persistente ao `backend`.
4. Criar serviço `frontend` usando `Dockerfile.frontend`.
5. Publicar ambos com domínio HTTPS do Northflank.
6. Atualizar as variáveis públicas do frontend com a URL real do backend.
