from __future__ import annotations

from app.schemas.auth import PermissionDefinition, RoleDefinition


PERMISSION_DEFINITIONS: list[PermissionDefinition] = [
    PermissionDefinition(key="dashboard.view", label="Ver visão geral", description="Acessa a página inicial e métricas gerais.", category="Portal"),
    PermissionDefinition(key="projects.view", label="Ver projetos", description="Lista projetos e detalhes técnicos.", category="Projetos"),
    PermissionDefinition(key="projects.create", label="Criar projetos", description="Envia arquivos e importa links para novos projetos.", category="Projetos"),
    PermissionDefinition(key="projects.process", label="Processar projetos", description="Dispara pipeline de análise e conversão.", category="Projetos"),
    PermissionDefinition(key="projects.delete", label="Excluir projetos", description="Remove versões do acervo.", category="Projetos"),
    PermissionDefinition(key="projects.download", label="Baixar projetos", description="Gera bundles e baixa artefatos finais.", category="Projetos"),
    PermissionDefinition(key="catalog.view", label="Ver catálogo", description="Acessa portfólio operacional e comercial.", category="Catálogo"),
    PermissionDefinition(key="queue.view", label="Ver fila", description="Acompanha processamento e status em andamento.", category="Operação"),
    PermissionDefinition(key="reports.view", label="Ver relatórios", description="Consulta relatórios, manifestos e diagnósticos.", category="Operação"),
    PermissionDefinition(key="knowledge.view", label="Ver base técnica", description="Consulta regras e incidentes aprendidos.", category="Conhecimento"),
    PermissionDefinition(key="knowledge.manage", label="Gerenciar base técnica", description="Registra incidentes e alimenta a base de conhecimento.", category="Conhecimento"),
    PermissionDefinition(key="stores.view", label="Ver lojas", description="Consulta integrações e canais de venda.", category="Lojas"),
    PermissionDefinition(key="stores.manage", label="Gerenciar lojas", description="Cria, edita e remove lojas e OAuth.", category="Lojas"),
    PermissionDefinition(key="stores.publish", label="Publicar rascunhos", description="Gera payloads de publicação para marketplaces.", category="Lojas"),
    PermissionDefinition(key="social_login.view", label="Ver login social", description="Consulta configuração dos provedores sociais.", category="Acesso"),
    PermissionDefinition(key="social_login.manage", label="Gerenciar login social", description="Configura provedores, segredos e botões sociais.", category="Acesso"),
    PermissionDefinition(key="ai_settings.view", label="Ver provedores IA", description="Consulta status e cadeia de fallback dos provedores de IA.", category="IA"),
    PermissionDefinition(key="ai_settings.manage", label="Gerenciar provedores IA", description="Ativa/desativa provedores de IA externos e ordem de fallback.", category="IA"),
    PermissionDefinition(key="users.view", label="Ver usuários", description="Consulta usuários, papéis e permissões.", category="Usuários"),
    PermissionDefinition(key="users.manage", label="Gerenciar usuários", description="Cria, edita, desativa e ajusta permissões.", category="Usuários"),
]


ROLE_TEMPLATES: list[RoleDefinition] = [
    RoleDefinition(
        key="master",
        label="Master",
        description="Acesso total ao sistema.",
        permissions=[item.key for item in PERMISSION_DEFINITIONS],
    ),
    RoleDefinition(
        key="admin",
        label="Administrador",
        description="Administra operação, lojas, login social e usuários.",
        permissions=[
            "dashboard.view",
            "projects.view",
            "projects.create",
            "projects.process",
            "projects.delete",
            "projects.download",
            "catalog.view",
            "queue.view",
            "reports.view",
            "knowledge.view",
            "knowledge.manage",
            "stores.view",
            "stores.manage",
            "stores.publish",
            "social_login.view",
            "social_login.manage",
            "ai_settings.view",
            "ai_settings.manage",
            "users.view",
            "users.manage",
        ],
    ),
    RoleDefinition(
        key="operator",
        label="Operador",
        description="Opera projetos e acompanha execução, sem administração de usuários.",
        permissions=[
            "dashboard.view",
            "projects.view",
            "projects.create",
            "projects.process",
            "projects.download",
            "catalog.view",
            "queue.view",
            "reports.view",
            "knowledge.view",
        ],
    ),
    RoleDefinition(
        key="sales",
        label="Comercial",
        description="Foco em catálogo, relatórios de venda e marketplaces.",
        permissions=[
            "dashboard.view",
            "projects.view",
            "projects.download",
            "catalog.view",
            "reports.view",
            "stores.view",
            "stores.manage",
            "stores.publish",
        ],
    ),
    RoleDefinition(
        key="viewer",
        label="Leitura",
        description="Consulta acervo, relatórios e catálogo sem alterar dados.",
        permissions=[
            "dashboard.view",
            "projects.view",
            "projects.download",
            "catalog.view",
            "queue.view",
            "reports.view",
            "stores.view",
        ],
    ),
]


def permission_keys() -> set[str]:
    return {item.key for item in PERMISSION_DEFINITIONS}


def role_map() -> dict[str, RoleDefinition]:
    return {item.key: item for item in ROLE_TEMPLATES}
