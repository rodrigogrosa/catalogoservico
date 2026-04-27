# SnapMaker3d Studio - Handoff Técnico Completo

Este documento é o ponto único de transição para um desenvolvedor humano assumir e evoluir a plataforma sem perda de contexto.

## 1) Escopo da plataforma

Objetivo operacional atual:

1. importar projeto 3D (upload local ou URL direta);
2. analisar e converter para fluxo Snapmaker U1;
3. gerar artefatos técnicos, previews e manifesto;
4. gerar ficha comercial e rascunho de anúncio;
5. integrar com marketplaces (principalmente Mercado Livre).

Domínios publicados:

- App: `https://app.euachei3d.com.br`
- API: `https://api.euachei3d.com.br`

## 2) Stack e arquitetura

### Backend

- Linguagem: Python 3.12/3.13
- Framework: FastAPI
- Servidor: Uvicorn
- Principais libs: `trimesh`, `numpy`, `pillow`, `meshio`, `httpx`, `orjson`
- Logging: JSON estruturado com `x-request-id`

### Frontend

- Next.js 15 + React 19 + TypeScript + Tailwind
- Proxy de API por rewrite (`/api/v1/*`)
- Fallback para backend direto quando proxy está instável

### Persistência

- Não usa banco relacional.
- Persistência em filesystem.
- Raiz obrigatória: `~/Downloads/Projetos3d/SnapMaker3d` (ou `/data/SnapMaker3d` em container).

### Multiagentes

- Orchestrator + agentes especializados (`Geometry`, `Snapmaker`, `Bambu`, `Materials`, `Colors`, `QA`, `Observability`, etc.).
- Serviços determinísticos para operações críticas (`conversion_service`, `mesh_analysis_service`, `preview_service`, `store_service`).

## 3) Estrutura crítica de pastas

```text
SnapMaker3d Studio/
├── backend/
│   ├── app/
│   │   ├── api/routes/
│   │   ├── core/
│   │   ├── services/
│   │   ├── schemas/
│   │   └── data/profiles/snapmaker_u1_v1.json
│   └── tests/
├── frontend/
│   ├── app/
│   ├── components/
│   └── lib/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── REGRESSION_TEST_PLAN.md
│   └── HANDOFF_DESENVOLVEDOR_COMPLETO.md
├── infra/northflank/
├── scripts/
├── Dockerfile.backend
├── Dockerfile.frontend
└── docker-compose.yml
```

Layout por projeto (runtime):

```text
<storage_root>/<slug>/<slug>_vNNN/
├── original/
├── processado/
├── export/
├── relatorios/
├── previews/
├── logs/
└── project_manifest.json
```

Dados globais de sistema:

```text
<storage_root>/
├── _system/users.json
├── _system/stores.json
├── _system/social_login.json
├── _system/ai_runtime.json
└── knowledge/
    ├── rules.json
    └── incidents.json
```

## 4) Variáveis de ambiente e chaves

Fonte principal de referência: `.env.example`, `infra/northflank/*.env.example`, `backend/app/core/config.py`, `frontend/lib/api.ts`.

### 4.1 Backend/API

| Variável | Obrigatória | Tipo | Segredo | Finalidade |
|---|---|---|---|---|
| `APP_ENV` | Sim | string | Não | Ambiente (`development`, `production`) |
| `BACKEND_HOST` | Sim | string | Não | Host do uvicorn |
| `BACKEND_PORT` | Sim | int | Não | Porta da API |
| `ALLOWED_ORIGINS` | Sim | CSV | Não | CORS do frontend |
| `PUBLIC_BACKEND_ORIGIN` | Sim | URL | Não | URL pública da API |
| `PUBLIC_FRONTEND_ORIGIN` | Sim | URL | Não | URL pública do app |
| `SNAPMAKER_STORAGE_ROOT` | Sim | path | Não | Persistência de projetos |
| `AUTH_TOKEN_SECRET` | Sim | string | Sim | Assinatura de sessão |
| `AUTH_TOKEN_TTL_HOURS` | Sim | int | Não | Expiração do token |
| `MASTER_USERNAME` | Sim | string | Sensível | Login master |
| `MASTER_PASSWORD` | Sim | string | Sim | Senha master |
| `MASTER_PASSWORD_ALIASES` | Não | CSV | Sim | Senhas alternativas master |
| `MAX_UPLOAD_SIZE_MB` | Sim | int | Não | Limite de upload |
| `MAX_PROJECT_FILES` | Sim | int | Não | Máx. arquivos por projeto |
| `MAX_ZIP_ENTRIES` | Sim | int | Não | Proteção anti-bomba zip |
| `MAX_ZIP_DEPTH` | Sim | int | Não | Profundidade máxima zip |
| `MAX_TRIANGLES` | Sim | int | Não | Limite de complexidade de malha |
| `STAGE_TIMEOUT_SECONDS` | Sim | int | Não | Timeout por etapa |

### 4.2 LLM e geração de mídia

| Variável | Obrigatória | Segredo | Finalidade |
|---|---|---|---|
| `OLLAMA_ENABLED` | Sim | Não | Liga/desliga LLM local |
| `OLLAMA_BASE_URL` | Sim | Não | Endpoint Ollama |
| `OLLAMA_MODEL` | Sim | Não | Modelo textual local |
| `OLLAMA_VISION_MODEL` | Não | Não | Modelo visual local |
| `OLLAMA_TIMEOUT_SECONDS` | Sim | Não | Timeout de chamada |
| `FREE_AI_ENABLED` | Sim | Não | Liga pipeline de IA gratuita |
| `FREE_AI_EXTERNAL_ENABLED` | Sim | Não | Habilita provedores externos |
| `FREE_AI_PROVIDER_ORDER` | Sim | Não | Ordem de fallback |
| `AI_GENERATION_TIMEOUT_SECONDS` | Sim | Não | Timeout global de geração |
| `POLLINATIONS_IMAGE_MODEL` | Não | Não | Modelo de imagem Pollinations |
| `POLLINATIONS_TEXT_MODEL` | Não | Não | Modelo textual Pollinations |
| `HUGGINGFACE_API_TOKEN` | Não | Sim | Token HF para fallback |
| `HUGGINGFACE_TEXT_MODEL` | Não | Não | Modelo textual HF |
| `HUGGINGFACE_IMAGE_MODEL` | Não | Não | Modelo de imagem HF |

### 4.3 OAuth social

| Provedor | Chaves exigidas |
|---|---|
| Google | `client_id`, `client_secret`, `redirect_uri` |
| Apple | `client_id`, `team_id`, `key_id`, `private_key`, `redirect_uri` |
| Instagram | `client_id`, `client_secret`, `redirect_uri` |

Observação: configuração persistida em `_system/social_login.json`.

### 4.4 Marketplace (Mercado Livre)

Campos usados no conector:

- `client_id`
- `client_secret`
- `redirect_uri`
- `authorization_code`
- `access_token`
- `refresh_token`
- `seller_id`

URLs padrão geradas pela API:

- Redirect OAuth: `https://api.euachei3d.com.br/api/v1/stores/oauth/mercado-livre/callback`
- Notificações: `https://api.euachei3d.com.br/api/v1/stores/webhooks/mercado-livre`

Observação: dados por usuário em `_system/stores.json`.

## 5) Credenciais e segurança (handoff)

Para repasse a novo dev:

1. não versionar segredos reais em Git;
2. compartilhar segredos via cofre (1Password/Bitwarden/Vault);
3. rotacionar ao trocar equipe:
   - `AUTH_TOKEN_SECRET`
   - `MASTER_PASSWORD`
   - `client_secret` dos provedores OAuth
   - tokens de marketplaces;
4. validar se callback/redirect de OAuth está com HTTPS e URL exata.

Checklist de segredos a entregar ao dev (fora do Git):

- credenciais Northflank (team/API token);
- variáveis de produção do backend e frontend;
- conta master operacional;
- credenciais Google/Apple/Instagram;
- credenciais Mercado Livre (app + seller OAuth);
- token HuggingFace (se usado em produção).

## 6) Permissões, papéis e governança

Permissões centrais:

- Projetos: `projects.view/create/process/delete/download`
- Catálogo: `catalog.view`
- Operação: `queue.view`, `reports.view`
- Conhecimento: `knowledge.view/manage`
- Lojas: `stores.view/manage/publish`
- Login social: `social_login.view/manage`
- IA: `ai_settings.view/manage`
- Usuários: `users.view/manage`

Papéis:

- `master`: acesso total
- `admin`: administração ampla
- `operator`: operação técnica
- `sales`: operação comercial/marketplace
- `viewer`: leitura

Regra importante já aplicada:

- somente `master` pode criar/editar/excluir usuários (`/api/v1/users/*` mutação exige `require_master`).

## 7) Endpoints principais

Base: `/api/v1`

### Auth e usuários

- `POST /auth/login`
- `GET /auth/me`
- `GET /auth/access-model`
- `GET /auth/providers`
- `GET /auth/social-config`
- `PUT /auth/social-config/{provider}`
- `GET|POST /auth/oauth/{provider}/callback`
- `GET /users`
- `POST /users` (master)
- `PUT /users/{provider}/{username}` (master)
- `DELETE /users/{provider}/{username}` (master)

### Projetos e pipeline

- `GET /projects`
- `GET /projects/{project_id}`
- `POST /projects/upload`
- `POST /projects/import-url`
- `POST /projects/{project_id}/process`
- `POST /projects/{project_id}/refresh-previews`
- `GET /projects/{project_id}/bundle`
- `GET /projects/{project_id}/compare/{other_project_id}`
- `DELETE /projects/{project_id}`

### Lojas e publicação

- `GET /stores/connectors`
- `GET /stores`
- `POST /stores`
- `PUT /stores/{store_id}`
- `DELETE /stores/{store_id}`
- `POST /stores/{store_id}/oauth/mercado-livre/start`
- `GET /stores/oauth/mercado-livre/callback`
- `POST /stores/webhooks/mercado-livre`
- `POST /stores/{store_id}/publish/{project_id}`
- `POST /stores/{store_id}/items/{item_id}/refresh-media/{project_id}`

### Saúde e observabilidade

- `GET /health`
- `GET /health/ready`

## 8) Fluxo operacional fim a fim

1. usuário autentica (master/local/social);
2. envia arquivo 3D;
3. backend grava em `original/` com versionamento;
4. parser seguro valida estrutura e dependências;
5. previews e manifesto inicial são gerados;
6. pipeline multiagente processa;
7. QA técnico calcula score final;
8. export + relatórios + bundle final são gerados;
9. catálogo comercial usa dados e imagens;
10. integração de loja monta payload e pode publicar.

## 9) Deploy (Northflank)

### Serviços

- `backend` via `Dockerfile.backend`, healthcheck `/api/v1/health/ready`
- `frontend` via `Dockerfile.frontend`, healthcheck `/`

### DNS recomendado

- `app.euachei3d.com.br` -> frontend
- `api.euachei3d.com.br` -> backend

### Arquivos de referência

- `infra/northflank/README.md`
- `infra/northflank/backend.env.example`
- `infra/northflank/frontend.env.example`

## 10) Observabilidade e troubleshooting

### Logs

- API escreve logs JSON no stdout com `request_id`.
- Cada projeto mantém `logs/processing.log`.

### Erros comuns e causa provável

| Erro | Causa comum | Ação |
|---|---|---|
| `Failed to fetch` no frontend | timeout/rede/proxy | conferir `x-request-id`, healthcheck e timeout |
| callback OAuth volta para localhost | `PUBLIC_FRONTEND_ORIGIN` incorreto | ajustar env no backend |
| bloqueio de publish no ML | token ausente/expirado, categoria faltante | refazer OAuth e validar `category_id` |
| imagens rejeitadas no ML | resolução, enquadramento, proporção | regenerar mídia marketplace e revisar seleção |

### Smoke test

Script pronto:

- `scripts/e2e_smoke.py`

Valida:

1. login
2. listagem de projetos
3. upload grande (42MB)
4. detalhe do projeto
5. cleanup por delete

## 11) Testes e qualidade

Backend (pytest):

- parsing, manifest, auth, usuários/permissões
- conversão Bambu, preview comercial, IA fallback
- stores/marketplace
- regressão operacional

Arquivos relevantes:

- `backend/tests/test_api.py`
- `backend/tests/test_conversion_service.py`
- `backend/tests/test_store_service.py`
- `backend/tests/test_users_permissions.py`
- `backend/tests/test_preview_marketplace_images.py`
- `docs/REGRESSION_TEST_PLAN.md`

## 12) Débitos técnicos e próximos passos prioritários

1. reduzir payload de `GET /projects` e `GET /projects/{id}` para evitar instabilidade em catálogos grandes;
2. separar geração pesada de previews em job assíncrono dedicado;
3. hardening do publish automático de marketplaces com validação de atributos obrigatórios por categoria;
4. implementar rotação e criptografia em repouso para credenciais de loja em `_system/stores.json`;
5. adicionar monitoramento ativo (Sentry/OTel) para erros de rede e timeout.

## 13) Passo a passo para novo desenvolvedor assumir

1. clonar repositório;
2. criar `.env` a partir de `.env.example` (sem segredos em git);
3. rodar `scripts/bootstrap.sh`;
4. subir stack local (`scripts/start-backend.sh` + `scripts/start-frontend.sh` ou `docker compose up --build`);
5. executar `pytest` no backend;
6. executar `scripts/e2e_smoke.py`;
7. validar login, upload, pipeline, catálogo e stores;
8. acessar ambiente publicado e testar callbacks OAuth reais.

---

## 14) Responsabilidades de manutenção contínua

- atualizar dependências críticas de segurança;
- revisar limites de upload e timeout conforme volume real;
- monitorar incidentes em `knowledge/incidents.json`;
- revisar regras preventivas de conversão para evitar regressões do Snapmaker Orca;
- validar periodicamente callbacks e tokens de integrações externas.

