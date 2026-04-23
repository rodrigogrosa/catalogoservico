# Plano de Regressão

Objetivo: impedir que erros já corrigidos no fluxo Bambu -> Snapmaker reapareçam sem detecção.

## Escopo mínimo obrigatório

1. Sanitização de parâmetros `3MF`
- `prime_tower_width` nunca pode sair inválido.
- `use_relative_e_distances` deve permanecer compatível com o perfil escolhido.
- valores negativos herdados do Bambu devem ser normalizados.

2. Geometria exportada
- `3D/3dmodel.model` precisa conter geometria legível pelo Snapmaker Orca.
- referências externas `p:path` devem ser embutidas quando necessário.
- objetos compostos no `build` devem ser achatados em itens que apontem para malhas diretas.

3. Primeira camada e suportes
- peças com área de contato reduzida devem sair com plano de adesão.
- overhangs críticos devem ligar suportes automaticamente.

4. Envelope e plating
- peças fora da área útil devem ser recentralizadas, divididas ou marcadas como pendência.
- exports multipartes não podem perder o vínculo com suas malhas.

5. Persistência e UX
- nunca sobrescrever artefatos sem versionamento.
- expor etapas detalhadas no frontend e na API.
- mostrar claramente a pasta de saída e os arquivos gerados.

## Casos de teste automatizados

- `backend/tests/test_conversion_service.py`
  - sanitização de parâmetros Bambu
  - nomes incrementais
  - suportes automáticos
  - adesão de primeira camada
  - inline de geometria externa
  - flatten de objetos compostos
  - split de plate excedido

- `backend/tests/test_progress_and_llm.py`
  - pipeline de etapas inclui LLM, relatórios e QA
  - atualização de etapa persiste início e conclusão
  - agente LLM faz fallback limpo quando indisponível

- `backend/tests/test_api.py`
  - health expõe runtime do LLM

## Casos de validação manual

1. Subir um `3MF` Bambu simples e confirmar:
- carregamento no Snapmaker Orca
- sem erro de geometria ausente
- sem erro de `prime_tower_width`

2. Subir um projeto com overhang:
- suportes automáticos devem aparecer no perfil exportado

3. Subir um projeto com base pequena:
- brim ou raft devem ser aplicados

4. Subir um projeto multipartes grande:
- split em múltiplos exports
- cada parte deve abrir sozinha no Orca

5. Verificar UI:
- cada etapa com barra própria
- status incremental durante a execução
- caminhos de saída visíveis

## Critério de aceite

Uma regressão é bloqueante quando qualquer um destes pontos falhar:
- Snapmaker Orca recusa o arquivo por falta de geometria
- parâmetros `3MF` inválidos voltam a aparecer
- suporte obrigatório não é inserido
- primeira camada fica sem estratégia de adesão quando requerida
- frontend perde a visibilidade das etapas
