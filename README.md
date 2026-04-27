# SnapMaker3d Studio

Sistema multiagente para preparação, análise, transformação, adaptação e exportação de modelos 3D para o fluxo da `Snapmaker U1`, com compatibilidade operacional voltada ao `Snapmaker Orca 2.3.0`.

## Estado atual do projeto

Esta fase evolui a base já existente sem reescrever o sistema do zero. O projeto agora inclui:

- upload simples e upload agrupado de arquivos dependentes;
- parsing robusto para `3MF`, `ZIP`, `STL`, `OBJ + MTL + texturas`;
- manifesto formal por projeto e snapshot reprodutível de execução;
- score de imprimibilidade;
- auditoria de decisões automáticas;
- transformações geométricas controladas;
- perfil formal versionado da `Snapmaker U1`;
- equivalência auditável de parâmetros `Bambu/3MF -> Snapmaker`;
- camada operacional de validação para export `3MF`;
- frontend com fila, progresso por etapa, comparação entre versões, bundle consolidado e perguntas bloqueantes;
- corpus inicial de testes e golden files;
- Dockerfiles, `docker-compose`, readiness check e bootstrap local.

## Arquitetura

Arquitetura detalhada: `docs/ARCHITECTURE.md`

### Camadas

1. `Frontend`
   - Next.js, React, TypeScript e Tailwind.
   - Upload, fila, progresso, score, comparação, bundles, galeria e perguntas bloqueantes.

2. `API`
   - FastAPI.
   - Endpoints de upload, processamento, comparação, bundle, conhecimento, health e readiness.

3. `Orquestração`
   - `OrchestratorAgent` controla sequência, bloqueios e consolidação.

4. `Agentes especialistas`
   - `GeometryAgent`
   - `SnapmakerAgent`
   - `TransformationAgent`
   - `BambuAgent`
   - `MaterialsAgent`
   - `ColorsAgent`
   - `KnowledgeAgent`
   - `LlmStrategyAgent`
   - `LlmRegressionAgent`
   - `ObservabilityAgent`
   - `QATechnicalAgent`

5. `Serviços determinísticos`
   - parsing, checksums, manifesto, storage, análise geométrica, transformação, conversão, preview, relatórios, bundle, auditoria, validação de export e LLM local.

6. `Persistência`
   - obrigatoriamente em `~/Downloads/Projetos3d/SnapMaker3d`
   - estrutura por projeto/versionamento:
     - `original/`
     - `processado/`
     - `export/`
     - `relatorios/`
     - `previews/`
     - `logs/`

## Perfil operacional Snapmaker U1

O perfil central da máquina está em:

- `backend/app/data/profiles/snapmaker_u1_v1.json`

Ele concentra:

- volume útil;
- nozzle padrão e suportados;
- presets por objetivo;
- defaults conservadores;
- regras por material;
- limitações conhecidas;
- slicer alvo `Snapmaker Orca 2.3.0`.

## Diretórios

```text
SnapMaker3d Studio/
├── .dockerignore
├── .env.example
├── Dockerfile.backend
├── Dockerfile.frontend
├── README.md
├── docker-compose.yml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── REGRESSION_TEST_PLAN.md
│   └── examples/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── data/
│   │   ├── schemas/
│   │   └── services/
│   │       └── agents/
│   ├── requirements.txt
│   ├── run.py
│   └── tests/
│       └── fixtures/
├── frontend/
│   ├── app/
│   ├── components/
│   └── lib/
└── scripts/
    ├── bootstrap.sh
    ├── start-backend.sh
    ├── start-frontend.sh
    ├── start-stack.sh
    └── process-library.py
```

## Principais capacidades implementadas

### Entrada e parsing

- valida `3MF/ZIP` quebrado;
- detecta XML interno inválido;
- detecta arquivos vazios;
- detecta STL truncado por heurística;
- valida OBJ, MTL e texturas relacionadas;
- identifica dependências ausentes;
- aceita múltiplos arquivos em um único projeto;
- tenta inferir unidade e marca ambiguidades.

### Geometria

- watertight;
- corpos desconectados;
- risco de overhang;
- risco de primeira camada;
- detalhes abaixo do nozzle;
- paredes finas por heurística;
- bridges e cavidades fechadas por aproximação;
- sugestão de orientação automática;
- reparo simples de malha.

### Transformações

- escala uniforme;
- base auxiliar;
- simplificação opcional;
- hollowing aproximado com shell e hole de escape;
- versionamento de cada artefato gerado.

### Conversão Bambu -> Snapmaker

- sanitização de `3MF` para compatibilidade com Snapmaker Orca;
- equivalência por parâmetro com status auditável;
- leitura rica de estrutura Bambu por heurística;
- inlining de geometria externa;
- normalização de layout;
- preservação parcial de intenção do build;
- relatório de perdas, fallbacks e aproximações.

### Snapmaker e operação real

- preset por objetivo;
- regras de material/nozzle;
- aderência de primeira camada;
- suporte automático;
- validação de export `3MF`;
- bundle ZIP consolidado por versão;
- readiness check.

### Autenticação e acesso

- login master local configurado por ambiente;
- rotas de projetos e conhecimento exigem Bearer token;
- provedores Google, Apple e Instagram expostos como contrato de OAuth;
- botões sociais aparecem na tela de login e ficam desativados até `client_id` e `redirect_uri` serem configurados.

### Observabilidade e auditoria

- `project_manifest.json`;
- snapshot de execução;
- logs textuais e JSONL;
- decisões automáticas persistidas;
- métricas por etapa;
- base de conhecimento operacional em disco.

## Modelos e artefatos principais

### Manifesto formal

Gerado como:

- `project_manifest.json`

Inclui:

- projeto, versão e origem;
- formatos de entrada;
- hashes;
- artefatos gerados;
- parâmetros finais;
- decisões automáticas;
- perguntas e respostas;
- limitações;
- snapshot.

### Snapshot de execução

Inclui:

- inputs;
- parâmetros finais;
- saídas dos agentes;
- prompts internos;
- fallbacks;
- riscos;
- artefatos.

### Score de imprimibilidade

Inclui:

- score numérico;
- nível `low/medium/high`;
- blockers;
- warnings;
- recomendações.

## Endpoints

### Autenticação

- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/providers`

### Saúde e readiness

- `GET /api/v1/health`
- `GET /api/v1/health/ready`

### Projetos

Exigem `Authorization: Bearer <token>`.

- `GET /api/v1/projects`
- `GET /api/v1/projects/{project_id}`
- `POST /api/v1/projects/upload`
- `POST /api/v1/projects/import-url`
- `POST /api/v1/projects/{project_id}/process`
- `GET /api/v1/projects/{project_id}/bundle`
- `GET /api/v1/projects/{project_id}/compare/{other_project_id}`

### Conhecimento operacional

- `GET /api/v1/knowledge/rules`
- `GET /api/v1/knowledge/incidents`
- `POST /api/v1/knowledge/incidents`

### Docs interativas

- `/docs`

## Exemplo de upload agrupado

Use o mesmo formulário para enviar:

- `modelo.obj`
- `modelo.mtl`
- `textura_01.png`
- `textura_02.jpg`

O backend mantém o conjunto no mesmo projeto, registra dependências e emite diagnóstico se faltar algum recurso.

## Exemplos prontos

Arquivos de exemplo desta fase:

- payload de processamento: `docs/examples/process-payload.json`
- relatório JSON: `docs/examples/report.json`
- relatório Markdown: `docs/examples/report.md`
- manifesto: `docs/examples/project_manifest.json`
- score: `docs/examples/printable_score.json`
- equivalência Bambu -> Snapmaker: `docs/examples/bambu_equivalence.json`
- perguntas bloqueantes: `docs/examples/blocking-questions.json`

## Frontend

### Telas principais

- Home com fila de processamento, cards de status e upload múltiplo.
- Login com acesso master e preparação para Google, Apple e Instagram.
- Tela do projeto com:
  - progresso geral;
  - barras por etapa;
  - score de imprimibilidade;
  - perguntas bloqueantes;
  - perguntas recomendadas;
  - comparação entre versões;
  - equivalência Bambu -> Snapmaker;
  - galeria de previews;
  - bundle ZIP consolidado;
  - caminhos de saída.

### Reprocessamento rápido

O painel lateral já permite reprocessar uma versão com variações como:

- PETG + brim/base auxiliar;
- perfil decorativo;
- ajuste automático para a mesa;
- hollowing aproximado;
- simplificação de microdetalhes.

## Variáveis de ambiente

Veja `.env.example`.

Variáveis principais:

- `MASTER_USERNAME`
- `MASTER_PASSWORD`
- `AUTH_TOKEN_SECRET`
- `AUTH_TOKEN_TTL_HOURS`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_REDIRECT_URI`
- `APPLE_OAUTH_CLIENT_ID`
- `APPLE_OAUTH_REDIRECT_URI`
- `INSTAGRAM_OAUTH_CLIENT_ID`
- `INSTAGRAM_OAUTH_REDIRECT_URI`
- `SNAPMAKER_STORAGE_ROOT`
- `PIPELINE_VERSION`
- `MAX_UPLOAD_SIZE_MB`
- `MAX_PROJECT_FILES`
- `MAX_ZIP_ENTRIES`
- `MAX_ZIP_DEPTH`
- `MAX_TRIANGLES`
- `STAGE_TIMEOUT_SECONDS`
- `OLLAMA_ENABLED`
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `FREE_AI_ENABLED`
- `FREE_AI_EXTERNAL_ENABLED`
- `FREE_AI_PROVIDER_ORDER`
- `AI_GENERATION_TIMEOUT_SECONDS`
- `POLLINATIONS_TEXT_MODEL`
- `POLLINATIONS_IMAGE_MODEL`
- `HUGGINGFACE_API_TOKEN`
- `HUGGINGFACE_TEXT_MODEL`
- `HUGGINGFACE_IMAGE_MODEL`

### IA gratuita com fallback no upload

Ao adicionar um novo projeto, o backend agora roda uma cadeia de IA para:

- enriquecer copy comercial usando metadados do projeto e preview da peça;
- gerar imagem comercial adicional para anúncio (`marketplace_ai_01.jpg`);
- trocar automaticamente de provedor em falha/quota.

Ordem padrão:

- `ollama` (local, sem custo recorrente)
- `pollinations` (API pública gratuita)
- `huggingface` (API com token, free tier quando disponível)

## Execução local

### Requisitos

- Python `3.12` ou `3.13`
- Node.js `20+`
- npm
- opcional: `ollama`

### Bootstrap

```bash
./scripts/bootstrap.sh
```

### Subir backend

```bash
./scripts/start-backend.sh
```

### Subir frontend

```bash
./scripts/start-frontend.sh
```

## Execução com Docker

### Subir stack

```bash
docker compose up --build
```

ou

```bash
./scripts/start-stack.sh
```

### Portas

- frontend: `3000`
- backend externo no Docker: `8010`
- backend interno no container: `8000`

### Healthchecks

- backend: `GET /api/v1/health/ready`
- frontend: `GET /`

## Testes

### Backend

```bash
cd backend
.venv/bin/pytest -q
```

### Cobertura atual de testes

- parsing robusto;
- manifesto e hashes;
- bundle ZIP;
- knowledge;
- progresso e LLM local;
- conversão Bambu/3MF;
- corpus mínimo de fixtures;
- golden file de equivalência;
- comparação entre versões;
- readiness.
- autenticação master e proteção de rotas;
- rejeição orientada de páginas públicas MakerWorld que não são arquivo direto.

## Importação por link MakerWorld

O campo de URL aceita links diretos de arquivo `.3mf`, `.zip`, `.stl`, `.obj`, `.step`, `.stp` e `.amf`.

Links de página pública do MakerWorld, como `/models/...`, podem retornar `403` por login ou Cloudflare. O sistema não tenta burlar esse bloqueio. Quando isso ocorrer:

- abra o link no navegador;
- faça login no MakerWorld se necessário;
- use `Download`, `Download 3MF` ou `All files`;
- envie o `.3mf` ou `.zip` baixado pelo upload normal.

## Corpus e golden files

Fixtures desta fase:

- `backend/tests/fixtures/valid_ascii.stl`
- `backend/tests/fixtures/truncated_ascii.stl`
- `backend/tests/fixtures/sample.obj`
- `backend/tests/fixtures/sample.mtl`
- `backend/tests/fixtures/golden_bambu_equivalence.json`

## Limitações honestas desta fase

- hollowing ainda é conservador e aproximado, não um kernel CAD completo;
- detecção de paredes finas, bridges e cavidades usa heurísticas geométricas, não simulação física completa;
- equivalência Bambu -> Snapmaker continua parcial por natureza;
- parsing de `STEP/STP` ainda exige adaptador CAD mais forte para fidelidade alta;
- preview por camada ainda é simplificado;
- cancelamento fino por etapa ainda pode ser expandido no futuro.

## Diretriz operacional

O sistema foi ajustado para priorizar segurança operacional:

- não assume equivalência perfeita;
- não inventa cor oficial sem base;
- não aplica mudança destrutiva sem registrar;
- não conclui export inconsistente sem `QA`;
- não sobrescreve artefatos anteriores;
- sempre gera manifesto, relatórios e rastreabilidade.
