"""Connector type definitions and required credential fields."""

# Mapping of connector type -> required credential fields
CONNECTOR_CREDENTIALS = {
    "GRAFANA": {
        "required": ["grafana_host", "grafana_api_key"],
        "optional": ["ssl_verify"],
        "cli_tool": None,
        "description": "Grafana dashboards, datasources, and alerts",
    },
    "GRAFANA_LOKI": {
        "required": ["grafana_host", "grafana_api_key"],
        "optional": ["ssl_verify"],
        "cli_tool": None,
        "description": "Grafana Loki log labels and queries",
    },
    "DATADOG": {
        "required": ["dd_api_key", "dd_app_key"],
        "optional": ["dd_api_domain"],
        "cli_tool": None,
        "description": "Datadog monitors, dashboards, services, and metrics",
    },
    "CLOUDWATCH": {
        "required": ["region"],
        "optional": ["aws_access_key", "aws_secret_key", "aws_assumed_role_arn"],
        "cli_tool": "aws",
        "description": "AWS CloudWatch metrics, logs, alarms, ECS, and RDS",
    },
    "EKS": {
        "required": ["region", "eks_cluster_name"],
        "optional": ["aws_access_key", "aws_secret_key", "aws_assumed_role_arn"],
        "cli_tool": "aws",
        "description": "Amazon EKS cluster metadata",
    },
    "GKE": {
        "required": ["gke_project_id", "gke_cluster_name", "gke_zone"],
        "optional": ["gke_service_account_json"],
        "cli_tool": "gcloud",
        "description": "Google GKE cluster metadata",
    },
    "KUBERNETES": {
        "required": ["cluster_name", "cluster_api_server", "cluster_token"],
        "optional": [],
        "cli_mode_optional": ["cluster_api_server", "cluster_token"],
        "cli_tool": "kubectl",
        "description": "Kubernetes namespaces, services, deployments, ingresses, HPAs",
    },
    "NEW_RELIC": {
        "required": ["nr_api_key", "nr_account_id"],
        "optional": [],
        "cli_tool": None,
        "description": "New Relic alert policies and entities",
    },
    "GITHUB": {
        "required": ["github_token"],
        "optional": ["github_org"],
        "cli_tool": "git",
        "description": "GitHub repos and org members",
    },
    "ARGOCD": {
        "required": ["argocd_server", "argocd_token"],
        "optional": [],
        "cli_tool": None,
        "description": "ArgoCD applications",
    },
    "JIRA_CLOUD": {
        "required": ["jira_url", "jira_email", "jira_api_token"],
        "optional": [],
        "cli_tool": None,
        "description": "Jira projects and issue types",
    },
    "JENKINS": {
        "required": ["jenkins_url", "jenkins_user", "jenkins_api_token"],
        "optional": [],
        "cli_tool": None,
        "description": "Jenkins jobs",
    },
    "ELASTIC_SEARCH": {
        "required": ["es_host"],
        "optional": ["es_api_key", "es_username", "es_password"],
        "cli_tool": None,
        "description": "Elasticsearch indices and field mappings",
    },
    "OPEN_SEARCH": {
        "required": ["os_host"],
        "optional": ["os_username", "os_password"],
        "cli_tool": None,
        "description": "OpenSearch indices and field mappings",
    },
    "POSTGRES": {
        "required": ["host", "port", "database", "user", "password"],
        "optional": [],
        "cli_tool": None,
        "description": "PostgreSQL tables and schemas",
    },
    "MONGODB": {
        "required": ["connection_string"],
        "optional": [],
        "cli_tool": None,
        "description": "MongoDB databases and collections",
    },
    "CLICKHOUSE": {
        "required": ["ch_host", "ch_port", "ch_user", "ch_password"],
        "optional": ["ch_database"],
        "cli_tool": None,
        "description": "ClickHouse tables and schemas",
    },
    "SQL_DATABASE_CONNECTION": {
        "required": ["connection_string"],
        "optional": [],
        "cli_tool": None,
        "description": "Generic SQL database tables and schemas",
    },
    "SIGNOZ": {
        "required": ["signoz_host", "signoz_api_key"],
        "optional": [],
        "cli_tool": None,
        "description": "SigNoz services and dashboards",
    },
    "SENTRY": {
        "required": ["sentry_api_key"],
        "optional": ["sentry_org"],
        "cli_tool": None,
        "description": "Sentry projects and issues",
    },
    "AZURE": {
        "required": ["azure_tenant_id", "azure_client_id", "azure_client_secret", "azure_subscription_id"],
        "optional": [],
        "cli_tool": "az",
        "description": "Azure cloud resources and monitoring",
    },
    "GCM": {
        "required": ["gcp_project_id", "gcp_service_account_json"],
        "optional": [],
        "cli_tool": "gcloud",
        "description": "Google Cloud Monitoring metrics",
    },
    "POSTHOG": {
        "required": ["posthog_host", "posthog_api_key"],
        "optional": [],
        "cli_tool": None,
        "description": "PostHog events and properties",
    },
    "VICTORIA_LOGS": {
        "required": ["vl_host"],
        "optional": ["vl_api_key"],
        "cli_tool": None,
        "description": "Victoria Logs fields and streams",
    },
    "CORALOGIX": {
        "required": ["coralogix_api_key", "coralogix_domain"],
        "optional": [],
        "cli_tool": None,
        "description": "Coralogix log fields and queries",
    },
}

# Directories created by `init`
RESOURCE_DIRS = [
    "connectors",
    "cross_references",
]

# CLI tool -> how to install hint
CLI_TOOL_INSTALL_HINTS = {
    "kubectl": "Install: https://kubernetes.io/docs/tasks/tools/",
    "aws": "Install: pip install awscli  or  brew install awscli",
    "az": "Install: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli",
    "gcloud": "Install: https://cloud.google.com/sdk/docs/install",
    "git": "Install: brew install git  or  apt install git",
}
