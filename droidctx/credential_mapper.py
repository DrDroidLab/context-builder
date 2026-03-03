"""Maps user-friendly YAML credential keys to extractor constructor kwargs.

The credentials.yaml uses simple, user-friendly key names. But each extractor
constructor has its own specific parameter names. This module handles the
translation between the two.
"""

from drdroid_debug_toolkit.core.protos.base_pb2 import Source

# Maps connector type string -> Source proto enum
CONNECTOR_TYPE_TO_SOURCE = {
    "GRAFANA": Source.GRAFANA,
    "GRAFANA_LOKI": Source.GRAFANA,
    "DATADOG": Source.DATADOG,
    "CLOUDWATCH": Source.CLOUDWATCH,
    "EKS": Source.EKS,
    "GKE": Source.GKE,
    "KUBERNETES": Source.KUBERNETES,
    "NEW_RELIC": Source.NEW_RELIC,
    "GITHUB": Source.GITHUB,
    "ARGOCD": Source.ARGOCD,
    "JIRA_CLOUD": Source.JIRA_CLOUD,
    "JENKINS": Source.JENKINS,
    "ELASTIC_SEARCH": Source.ELASTIC_SEARCH,
    "OPEN_SEARCH": Source.OPEN_SEARCH,
    "POSTGRES": Source.POSTGRES,
    "MONGODB": Source.MONGODB,
    "CLICKHOUSE": Source.CLICKHOUSE,
    "SQL_DATABASE_CONNECTION": Source.SQL_DATABASE_CONNECTION,
    "SIGNOZ": Source.SIGNOZ,
    "SENTRY": Source.SENTRY,
    "AZURE": Source.AZURE,
    "GCM": Source.GCM,
    "POSTHOG": Source.POSTHOG,
    "VICTORIA_LOGS": Source.VICTORIA_LOGS,
    "CORALOGIX": Source.CORALOGIX,
    "BASH": Source.BASH,
}

# Maps YAML credential keys -> extractor constructor kwargs.
# Only entries where the YAML key differs from the extractor kwarg need mapping.
# If a connector type is not listed here, YAML keys are passed through as-is.
CREDENTIAL_KEY_MAPPINGS = {
    "KUBERNETES": {
        "cluster_api_server": "api_server",
        "cluster_token": "token",
        "cluster_name": None,  # Not used by extractor, drop it
    },
    "GITHUB": {
        "github_token": "api_key",
        "github_org": "org",
    },
    "JIRA_CLOUD": {
        "jira_url": "jira_domain",
        "jira_api_token": "jira_cloud_api_key",
        "jira_email": "jira_email",
    },
    "JENKINS": {
        "jenkins_url": "url",
        "jenkins_user": "username",
        "jenkins_api_token": "api_token",
    },
    "ELASTIC_SEARCH": {
        "es_host": "host",
        "es_api_key": "api_key",
        "es_username": "username",
        "es_password": "password",
    },
    "OPEN_SEARCH": {
        "os_host": "host",
        "os_username": "username",
        "os_password": "password",
    },
    "SENTRY": {
        "sentry_api_key": "api_key",
        "sentry_org": "org_slug",
    },
    "POSTHOG": {
        "posthog_host": "posthog_host",
        "posthog_api_key": "personal_api_key",
    },
    "SIGNOZ": {
        "signoz_host": "signoz_api_url",
        "signoz_api_key": "signoz_api_token",
    },
    "GKE": {
        "gke_project_id": "project_id",
        "gke_cluster_name": None,  # Not used by extractor
        "gke_zone": None,  # Not used by extractor
        "gke_service_account_json": "service_account_json",
    },
    "GCM": {
        "gcp_project_id": "project_id",
        "gcp_service_account_json": "service_account_json",
    },
    "EKS": {
        "eks_cluster_name": None,  # Dropped, not used by extractor
    },
    "NEW_RELIC": {
        "nr_account_id": "nr_app_id",
    },
    "AZURE": {
        "azure_tenant_id": "tenant_id",
        "azure_client_id": "client_id",
        "azure_client_secret": "client_secret",
        "azure_subscription_id": "subscription_id",
    },
    "CLICKHOUSE": {
        "ch_host": "host",
        "ch_port": "port",
        "ch_user": "user",
        "ch_password": "password",
        "ch_database": None,  # Not a constructor arg
    },
    "CORALOGIX": {
        "coralogix_api_key": "api_key",
        "coralogix_domain": "domain",
    },
    "VICTORIA_LOGS": {
        "vl_host": "VICTORIA_LOGS_HOST",
        "vl_api_key": "VICTORIA_LOGS_HEADERS",
    },
}


def yaml_creds_to_extractor_kwargs(connector_type: str, yaml_config: dict) -> dict:
    """Convert user YAML credential config to extractor constructor kwargs.

    Strips the 'type' field and maps keys according to CREDENTIAL_KEY_MAPPINGS.
    """
    kwargs = {}
    mapping = CREDENTIAL_KEY_MAPPINGS.get(connector_type, {})

    for key, value in yaml_config.items():
        if key == "type":
            continue

        if key in mapping:
            mapped_key = mapping[key]
            if mapped_key is None:
                continue  # Explicitly dropped
            kwargs[mapped_key] = value
        else:
            kwargs[key] = value

    return kwargs


def get_source_enum(connector_type: str) -> Source:
    """Get the Source proto enum for a connector type string."""
    source = CONNECTOR_TYPE_TO_SOURCE.get(connector_type)
    if source is None:
        raise ValueError(f"Unknown connector type: {connector_type}")
    return source
